"""Single local supervisor with SQLite snapshots and real subprocess telemetry."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('coordinator', 'worker', 'evaluator', 'reflector', 'reviewer')
TASKS = {'coordinator': 'Inspect assets and record hashes', 'worker': 'Run JavaScript regression tests', 'evaluator': 'Run trusted Python installer tests', 'reflector': 'Analyze actual test evidence', 'reviewer': 'Review evidence and hash artifacts'}
TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_bindings(registry):
    if not isinstance(registry, dict) or not isinstance(registry.get('agents'), list) or len(registry['agents']) > 30:
        raise ValueError('Invalid agent registry')
    enabled, ids = {}, set()
    for agent in registry['agents']:
        if not isinstance(agent, dict) or not isinstance(agent.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', agent['id']) or agent['id'] in ids or not isinstance(agent.get('name'), str) or not 1 <= len(agent['name']) <= 80 or agent.get('role') not in ROLES or type(agent.get('enabled')) is not bool:
            raise ValueError('Invalid agent identity, role or enabled flag')
        ids.add(agent['id'])
        if agent['enabled']:
            if agent['role'] in enabled:
                raise ValueError('This fixed workflow requires exactly one enabled agent for each role')
            enabled[agent['role']] = {'id': agent['id'], 'name': agent['name'], 'role': agent['role']}
    if set(enabled) != set(ROLES):
        raise ValueError('Enable one coordinator, worker, evaluator, reflector and reviewer before starting')
    return [enabled[role] for role in ROLES]


class RuntimeService:
    def __init__(self, root=ROOT, command_factory=None, stage_timeout=120):
        self.root = Path(root).resolve()
        self.local = self.root / '.local'
        self.local.mkdir(exist_ok=True)
        self.lock_file = (self.local / 'runtime.lock').open('a+')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            raise RuntimeError('Another runtime supervisor is already running for this checkout')
        self.db = self.local / 'runtime.sqlite3'
        self.lock = threading.RLock()
        self.csrf_token = secrets.token_urlsafe(32)
        self.service_id = str(uuid.uuid4())
        self.command_factory = command_factory or self.native_command
        self.stage_timeout = stage_timeout
        self.thread = None
        self.process = None
        self.cancel_event = threading.Event()
        self.current = None
        self.closed = False
        from debug_log import DebugLog
        self.logs = DebugLog(self.root)
        self.browser_log_times = []
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE, data TEXT NOT NULL, created TEXT NOT NULL)')
            rows = db.execute('SELECT id, data FROM runs').fetchall()
            for identifier, raw in rows:
                run = json.loads(raw)
                if run['status'] not in TERMINAL:
                    run.update(status='interrupted', endedAt=now(), updatedAt=now())
                    for agent in run['agents']:
                        if agent['status'] in ('queued', 'running'):
                            agent.update(status='interrupted', processAlive=None, updatedAt=now(), error='Supervisor restarted; previous process state is unconfirmed')
                    db.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), identifier))
        from skill_store import SkillStore
        self.skills = SkillStore(self)
        from ollama_bridge import OllamaBridge
        from llm_store import LlmStore
        self.ollama = OllamaBridge(self.root)
        self.ollama.recover_warmup()
        self.llm = LlmStore(self)
        self.logs.append('runtime', 'INFO', 'Local runtime service started', details={'serviceId': self.service_id})

    @staticmethod
    def timestamp():
        return now()

    @staticmethod
    def native_command(role, path):
        filename = 'llm_agents.py' if (path / 'llm-config.json').is_file() else 'skill_agents.py' if (path / 'skill-config.json').is_file() else 'native_agents.py'
        return [sys.executable, str(ROOT / 'scripts' / filename), '--role', role, '--run-dir', str(path)]

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def persist(self):
        self.current['updatedAt'] = now()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)', (self.current['id'], self.current['requestId'], json.dumps(self.current), self.current['createdAt']))

    def event(self, agent, message):
        self.current['events'].append({'at': now(), 'agentId': agent['id'] if agent else None, 'text': message})
        self.current['events'] = self.current['events'][-200:]
        level = 'ERROR' if message.startswith(('Failed:', 'Supervisor error:')) or 'status: failed' in message or message.startswith('failed;') else 'WARNING' if 'cancel' in message.lower() else 'INFO'
        self.logs.append(agent['role'] if agent else 'runtime', level, message, self.current['id'],
                         {'task': self.current.get('task'), 'agentId': agent['id'] if agent else None})

    def get_run(self, identifier):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise KeyError('Run not found')
            return self.decorate(json.loads(row[0]))

    def decorate(self, run):
        end = run.get('endedAt') or now()
        elapsed = max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(run['createdAt'])).total_seconds())
        active_agent = next((a for a in run['agents'] if a['status'] == 'running'), None)
        run['executionProgress'] = {'elapsedSeconds': round(elapsed, 1),
            'completedStages': sum(a['status'] == 'completed' for a in run['agents']),
            'totalStages': len(run['agents']), 'stage': active_agent['role'] if active_agent else None,
            'heartbeatAt': active_agent['updatedAt'] if active_agent else run['updatedAt']}
        if run.get('task') == 'skill-evolution':
            path = self.local / 'runs' / run['id'] / 'progress.json'
            if path.is_file():
                try:
                    run['skillProgress'] = json.loads(path.read_text())
                except (ValueError, OSError):
                    pass
        if run.get('task') == 'llm-evolution':
            path = self.local / 'runs' / run['id'] / 'llm-progress.json'
            if path.is_file():
                try:
                    run['llmProgress'] = json.loads(path.read_text())
                except (ValueError, OSError):
                    pass
        if run['status'] in ('failed', 'cancelled', 'interrupted'):
            run['error'] = next((a['error'] for a in run['agents'] if a.get('error')), None)
        return run

    def close_model_call(self, directory, status, error):
        """Finalize evidence only after the worker is stopped; no concurrent writer."""
        from skill_engine import write
        path = directory / 'llm-progress.json'
        if not path.exists():
            return
        state = json.loads(path.read_text())
        call = state.get('lastCall')
        if not call or call.get('status') != 'running':
            return
        call.update(status=status, error=error, finishedAt=time.time(),
                    elapsedMs=round((time.time() - call['startedAt']) * 1000, 3))
        calls_path = directory / 'llm-calls.json'
        calls = json.loads(calls_path.read_text())
        calls[-1].update({k: v for k, v in call.items() if k not in ('request', 'response')})
        write(calls_path, calls)
        state['failedCalls'] = sum(c['status'] == 'failed' for c in calls)
        write(path, state)
        self.logs.append('llm', 'ERROR' if status == 'failed' else 'WARNING',
            f'Model call #{call["id"]} {status}: {error}', directory.name,
            {'elapsedMs': call['elapsedMs'], 'timeoutSeconds': call.get('timeoutSeconds')})

    def snapshot(self):
        with self.lock, self.connect() as db:
            runs = [json.loads(row[0]) for row in db.execute('SELECT data FROM runs ORDER BY created DESC LIMIT 10')]
        with self.lock, self.connect() as db:
            skill_runs = []
            for row in db.execute('SELECT data FROM runs ORDER BY created DESC'):
                run = json.loads(row[0])
                if run.get('task') == 'skill-evolution':
                    skill_runs.append(run)
                    if len(skill_runs) == 10:
                        break
            workspace = self.skills.snapshot()
            workspace.update(latestRun=self.decorate(skill_runs[0]) if skill_runs else None,
                             runs=[{'id': r['id'], 'status': r['status'], 'createdAt': r['createdAt'], 'baselineVersionId': r['skillConfig']['baseline']['id'], 'selectedId': r.get('skillResult', {}).get('selectedId'), 'eligible': r.get('skillResult', {}).get('eligible')} for r in skill_runs])
        with self.lock, self.connect() as db:
            llm_runs = [json.loads(r[0]) for r in db.execute('SELECT data FROM runs ORDER BY created DESC') if json.loads(r[0]).get('task') == 'llm-evolution'][:10]
            llm_workspace = self.llm.snapshot()
            llm_workspace.update(latestRun=self.decorate(llm_runs[0]) if llm_runs else None, runs=[{'id': r['id'], 'status': r['status'], 'createdAt': r['createdAt']} for r in llm_runs])
        return {'schemaVersion': 1, 'mode': 'native-tools', 'serviceId': self.service_id, 'serverTime': now(), 'latestRun': self.decorate(runs[0]) if runs else None, 'runs': [{'id': r['id'], 'status': r['status'], 'task': r.get('task', 'project-health'), 'createdAt': r['createdAt']} for r in runs], 'skills': workspace, 'llm': llm_workspace,
                'provider': {'revision': self.ollama.state()['revision'], 'config': self.ollama.state()['config'], 'busy': self.ollama.operation.locked(), 'warmup': self.ollama.warmup_status()}}

    def start(self, registry, request_id, task='project-health', options=None):
        agents = validate_bindings(registry)
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
            raise ValueError('Invalid idempotency request ID')
        if task not in ('project-health', 'skill-evolution', 'llm-evolution') or (task == 'project-health' and options is not None):
            raise ValueError('Unsupported fixed workflow')
        submission_hash = hashlib.sha256(json.dumps({'agents': agents, 'task': task, 'options': options}, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if self.closed:
                raise RuntimeError('Runtime service is stopping')
            with self.connect() as db:
                prior = db.execute('SELECT data FROM runs WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                existing = json.loads(prior[0])
                if existing.get('submissionHash', submission_hash) != submission_hash or existing.get('task') != task:
                    raise RuntimeError('Idempotency request ID is already bound to a different submission')
                return self.decorate(existing)
            if self.current and self.current['status'] not in TERMINAL:
                raise RuntimeError('A workflow is already running; cancel or wait before starting another')
            config = self.skills.freeze(options) if task == 'skill-evolution' else self.llm.freeze(options) if task == 'llm-evolution' else None
            from skill_agents import TASKS as SKILL_TASKS
            from llm_engine import TASKS as LLM_TASKS
            tasks = LLM_TASKS if task == 'llm-evolution' else SKILL_TASKS if config else TASKS
            if task == 'llm-evolution':
                if not self.ollama.operation.acquire(blocking=False):
                    raise RuntimeError('An Ollama request is already running; wait first')
                agents.sort(key=lambda a: ('coordinator', 'worker', 'reflector', 'evaluator', 'reviewer').index(a['role']))
            try:
                identifier = 'RUN-' + str(uuid.uuid4())
                directory = self.local / 'runs' / identifier
                directory.mkdir(parents=True)
                (directory / 'agents.json').write_text(json.dumps(agents, indent=2))
                if config:
                    (directory / ('llm-config.json' if task == 'llm-evolution' else 'skill-config.json')).write_text(json.dumps(config, indent=2, ensure_ascii=False))
                timestamp = now()
                self.current = {'id': identifier, 'requestId': request_id, 'submissionHash': submission_hash, 'task': task, 'mode': 'native-tools', 'status': 'queued', 'createdAt': timestamp, 'updatedAt': timestamp, 'endedAt': None, 'checksPassed': None, 'agents': [{**a, 'adapter': 'ollama-skill-role' if task == 'llm-evolution' else 'native-tool-agent', 'status': 'queued', 'task': tasks[a['role']], 'pid': None, 'processAlive': False, 'startedAt': None, 'endedAt': None, 'updatedAt': timestamp, 'exitCode': None, 'error': None, 'logTail': ''} for a in agents], 'events': [], 'artifacts': []}
                if config:
                    self.current['llmConfig' if task == 'llm-evolution' else 'skillConfig'] = config
                self.event(None, f'Queued actual {task} workflow; ' + ('explicit model calls, no GEPA adapter' if task == 'llm-evolution' else 'no LLM or GEPA calls'))
                self.persist()
                self.cancel_event.clear()
                self.thread = threading.Thread(target=self.execute, args=(directory,), daemon=True)
                self.thread.start()
                return copy.deepcopy(self.current)
            except Exception:
                if task == 'llm-evolution':
                    self.ollama.operation.release()
                raise

    def stop_process(self):
        process = self.process
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)

    def cancel(self, identifier):
        with self.lock:
            run = self.get_run(identifier)
            if run['status'] in TERMINAL:
                return run
            if not self.current or self.current['id'] != identifier:
                raise RuntimeError('Run is not owned by this supervisor')
            self.cancel_event.set()
            self.event(None, 'Cancellation requested; terminating active process group')
            self.persist()
            return copy.deepcopy(self.current)

    def execute(self, directory):
        provider_leased = self.current.get('task') == 'llm-evolution'
        workflow_started = time.monotonic()
        try:
            with self.lock:
                self.current['status'] = 'running'
                self.persist()
            for agent in self.current['agents']:
                if self.cancel_event.is_set():
                    break
                log = directory / (agent['role'] + '.log')
                log_offset = 0
                with self.lock:
                    agent.update(status='running', startedAt=now(), updatedAt=now())
                    self.event(agent, 'Starting: ' + agent['task'])
                    self.persist()
                try:
                    with log.open('w') as stream:
                        with self.lock:
                            if self.cancel_event.is_set():
                                break
                            self.process = subprocess.Popen(self.command_factory(agent['role'], directory), cwd=self.root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                            agent.update(pid=self.process.pid, processAlive=True)
                            self.persist()
                        started = time.monotonic()
                        timed_out = False
                        timeout_error = None
                        while self.process.poll() is None:
                            if self.cancel_event.wait(0.25):
                                self.stop_process()
                            elif (self.current.get('task') == 'llm-evolution' and time.monotonic() - workflow_started > self.current['llmConfig']['maxSeconds']) or (self.current.get('task') != 'llm-evolution' and time.monotonic() - started > self.stage_timeout):
                                timed_out = True
                                timeout_error = 'Workflow time limit exceeded' if provider_leased else 'Stage timed out'
                                self.stop_process()
                            elif provider_leased:
                                call = self.decorate(copy.deepcopy(self.current)).get('llmProgress', {}).get('lastCall')
                                if call and call.get('status') == 'running' and call.get('deadlineEpoch', float('inf')) <= time.time():
                                    timed_out = True
                                    timeout_error = f'Model call #{call["id"]} exceeded its {call["timeoutSeconds"]}s time limit; no further requests were sent'
                                    self.stop_process()
                            with self.lock:
                                agent.update(updatedAt=now(), processAlive=self.process.poll() is None, logTail=self.tail(log))
                                self.persist()
                            log_offset = self.capture_log(agent, log, log_offset)
                        code = self.process.wait()
                    with self.lock:
                        tail = self.tail(log)
                        self.capture_log(agent, log, log_offset)
                        error = timeout_error if timed_out else (tail.strip().splitlines()[-1][:1500] if tail.strip() else 'Process exited with an error') if code and not self.cancel_event.is_set() else None
                        agent.update(status='cancelled' if self.cancel_event.is_set() else 'failed' if timed_out or code else 'completed', exitCode=code, processAlive=False, endedAt=now(), updatedAt=now(), logTail=tail, error=error)
                        if provider_leased and agent['status'] in ('failed', 'cancelled'):
                            self.close_model_call(directory, agent['status'], error or 'Cancelled by user; no further requests were sent')
                        self.event(agent, f"{agent['status']}; PID {agent['pid']}; exit {code}")
                        self.process = None
                        self.persist()
                    if agent['status'] != 'completed':
                        break
                except Exception as exc:
                    self.stop_process()
                    with self.lock:
                        agent.update(status='failed', error=str(exc), processAlive=False, endedAt=now(), updatedAt=now())
                        self.event(agent, 'Failed: ' + str(exc))
                        self.persist()
                    break
            with self.lock:
                for agent in self.current['agents']:
                    if agent['status'] in ('queued', 'running'):
                        agent.update(status='cancelled' if self.cancel_event.is_set() else 'skipped', updatedAt=now(), endedAt=now())
                failed = any(a['status'] == 'failed' for a in self.current['agents'])
                self.current.update(status='cancelled' if self.cancel_event.is_set() else 'failed' if failed else 'completed', endedAt=now())
                review = directory / 'review.json'
                if review.exists():
                    result = json.loads(review.read_text())
                    self.current['checksPassed'] = result['checksPassed']
                    if self.current.get('task') in ('skill-evolution', 'llm-evolution'):
                        self.current['llmResult' if self.current['task'] == 'llm-evolution' else 'skillResult'] = result
                    if not self.current['checksPassed'] and self.current['status'] == 'completed':
                        self.current['status'] = 'failed'
                        self.event(None, 'Workflow finished but trusted checks failed')
                self.current['artifacts'] = sorted(p.name for p in directory.iterdir() if p.is_file())
                self.event(None, 'Workflow terminal status: ' + self.current['status'])
                self.persist()
        except Exception as exc:
            self.stop_process()
            with self.lock:
                self.current.update(status='failed', endedAt=now())
                for agent in self.current['agents']:
                    if agent['status'] in ('queued', 'running'):
                        agent.update(status='failed' if agent['status'] == 'running' else 'skipped', processAlive=False, endedAt=now(), updatedAt=now(), error='Supervisor failed')
                self.event(None, 'Supervisor error: ' + str(exc))
                self.persist()

        finally:
            if provider_leased:
                self.ollama.operation.release()

    @staticmethod
    def tail(path):
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 8192))
            return stream.read(8192).decode(errors='replace')

    def capture_log(self, agent, path, offset):
        with path.open('rb') as stream:
            stream.seek(offset); data = stream.read(65536); offset += len(data)
        for line in data.decode(errors='replace').splitlines():
            if line.strip():
                self.logs.append(agent['role'], 'ERROR' if line.startswith(('Traceback', 'ValueError:', 'TimeoutError:', 'RuntimeError:')) else 'DEBUG',
                    line, self.current['id'], {'source': 'subprocess', 'artifact': path.name, 'truncated': len(line) > 2048})
        return offset

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.cancel_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():
            self.stop_process()
            self.thread.join(timeout=3)
        self.ollama.close()
        self.logs.append('runtime', 'INFO', 'Local runtime service stopped')
        fcntl.flock(self.lock_file, fcntl.LOCK_UN)
        self.lock_file.close()
