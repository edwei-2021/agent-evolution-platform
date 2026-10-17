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
from native_check_plan import ROLE_CLEANUP_SECONDS, DEFAULT_ROLE_SECONDS

ROOT = Path(__file__).resolve().parents[1]
ROLES = ('coordinator', 'worker', 'evaluator', 'reflector', 'reviewer')
TASKS = {'coordinator': 'Inspect assets and record hashes', 'worker': 'Run JavaScript regression tests', 'evaluator': 'Run trusted Python installer tests', 'reflector': 'Analyze actual test evidence', 'reviewer': 'Review evidence and hash artifacts'}
MODEL_TASKS = ('llm-evolution', 'nanobot-repair', 'gepa-evolution')
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
    def __init__(self, root=ROOT, command_factory=None, stage_timeout=DEFAULT_ROLE_SECONDS):
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
        self.native_checks = command_factory is None
        self.stage_timeout = stage_timeout
        self.thread = None
        self.process = None
        self.cancel_event = threading.Event()
        self.completion_event = threading.Event()
        self.current = None
        self.closed = False
        self.discovery_lock = threading.Lock()
        self.discovery_thread = None
        self.discovery_identity = None
        from debug_log import DebugLog
        self.logs = DebugLog(self.root)
        from diagnostic_log import DiagnosticLog
        self.diagnostics = DiagnosticLog(self.root)
        self.logs.keep_open()
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
        from repair_store import RepairStore
        self.repair = RepairStore(self)
        from gepa_store import GepaStore
        self.gepa = GepaStore(self)
        from challenge_bank import ChallengeBank
        self.challenges = ChallengeBank(self)
        self.logs.append('runtime', 'INFO', 'Local runtime service started', details={'serviceId': self.service_id})

    @staticmethod
    def timestamp():
        return now()

    @staticmethod
    def native_command(role, path):
        if (path / 'gepa-config.json').is_file():
            config = json.loads((path / 'gepa-config.json').read_text())
            return [config['sdk']['python'], str(ROOT / 'scripts/gepa_agents.py'), '--role', role, '--run-dir', str(path)]
        if (path / 'repair-config.json').is_file():
            config = json.loads((path / 'repair-config.json').read_text())
            return [config['sdk']['python'], str(ROOT / 'scripts/repair_agents.py'), '--role', role, '--run-dir', str(path)]
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
        # This is a database snapshot, not a reference to mutable self.current.
        # Keep slow SQLite/progress-file reads out of the supervisor mutex so
        # frequent polling cannot block process state updates or cancellation.
        with self.connect() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise KeyError('Run not found')
            run = json.loads(row[0])
        return self.decorate(run)

    def wait_for_terminal(self, identifier, timeout):
        """Wait without database polling, then read the persisted final state.
        Completion is signalled after model-slot cleanup, including failures.
        """
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0 < timeout <= 7300:
            raise ValueError('Use a bounded positive terminal wait')
        with self.lock:
            active = self.current and self.current['id'] == identifier
            event = self.completion_event if active else None
        if event is not None:
            if not event.wait(timeout):
                raise TimeoutError('Workflow terminal wait exceeded its bounded budget')
        result = self.get_run(identifier)
        if result['status'] not in TERMINAL:
            raise RuntimeError('Completion has no persisted terminal evidence')
        return result

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
        if run.get('task') == 'nanobot-repair':
            path = self.local / 'runs' / run['id'] / 'repair-progress.json'
            if path.is_file():
                try: run['repairProgress'] = json.loads(path.read_text())
                except (ValueError, OSError): pass
        if run.get('task') == 'gepa-evolution':
            path = self.local / 'runs' / run['id'] / 'gepa-progress.json'
            if path.is_file():
                try: run['gepaProgress'] = json.loads(path.read_text())
                except (ValueError, OSError): pass
        if run['status'] in ('failed', 'cancelled', 'interrupted'):
            run['error'] = next((a['error'] for a in run['agents'] if a.get('error')), None)
        return run

    def close_model_call(self, directory, status, error):
        """Finalize evidence only after the worker is stopped; no concurrent writer."""
        from skill_engine import write
        prefix = 'gepa' if (directory / 'gepa-config.json').exists() else 'repair' if (directory / 'repair-config.json').exists() else 'llm'
        path = directory / (prefix + '-progress.json')
        if not path.exists():
            return
        state = json.loads(path.read_text())
        call = state.get('lastCall')
        if not call or call.get('status') != 'running':
            return
        call.update(status=status, error=error, finishedAt=time.time(),
                    elapsedMs=round((time.time() - call['startedAt']) * 1000, 3))
        calls_path = directory / (prefix + '-calls.json')
        calls = json.loads(calls_path.read_text())
        calls[-1].update({k: v for k, v in call.items() if k not in ('request', 'response')})
        write(calls_path, calls)
        state['failedCalls'] = sum(c['status'] == 'failed' for c in calls)
        write(path, state)
        self.logs.append('gepa' if prefix == 'gepa' else 'nanobot' if prefix == 'repair' else 'llm', 'ERROR' if status == 'failed' else 'WARNING',
            f'Model call #{call["id"]} {status}: {error}', directory.name,
            {'elapsedMs': call['elapsedMs'], 'timeoutSeconds': call.get('timeoutSeconds')})

    def sdk_snapshot(self):
        """Observe readiness immediately; one background discovery per window.

        Dispatch still uses the synchronous, pinned SDK probes in freeze().
        Never hold the workflow mutex while importing optional packages.
        """
        from repair_runtime import sdk_status
        from gepa_runtime import gepa_status
        sdk = sdk_status(self.root, cached_only=True)
        optimizer = gepa_status(self.root, sdk, cached_only=True)
        try:
            stamp = Path(sdk['python']).stat().st_mtime_ns
        except OSError:
            stamp = 0
        identity = (int(time.monotonic() // 300), sdk['python'], stamp)
        with self.discovery_lock:
            pending = sdk.get('errorCode') == 'not_probed' or optimizer.get('errorCode') == 'not_probed'
            if (pending and not self.closed and self.discovery_identity != identity
                    and (self.discovery_thread is None or not self.discovery_thread.is_alive())):
                self.discovery_identity = identity
                def discover():
                    try:
                        observed = sdk_status(self.root)
                        gepa_status(self.root, observed)
                    except Exception as exc:
                        # A read endpoint must not fail because an optional
                        # environment changed while discovery was running.
                        if not self.closed:
                            self.logs.append('runtime', 'ERROR', 'SDK discovery failed',
                                             details={'error': str(exc)})
                self.discovery_thread = threading.Thread(target=discover, name='sdk-discovery', daemon=True)
                self.discovery_thread.start()
        return sdk, optimizer

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
        with self.lock, self.connect() as db:
            repair_runs = [json.loads(r[0]) for r in db.execute('SELECT data FROM runs ORDER BY created DESC') if json.loads(r[0]).get('task') == 'nanobot-repair'][:10]
        sdk, optimizer = self.sdk_snapshot()
        repair_workspace = {'engine': 'nanobot-python-repair-v1', 'sdk': sdk, 'latestRun': self.decorate(repair_runs[0]) if repair_runs else None, 'runs': [{'id': r['id'], 'status': r['status'], 'createdAt': r['createdAt']} for r in repair_runs]}
        with self.lock, self.connect() as db:
            gepa_runs = [json.loads(r[0]) for r in db.execute('SELECT data FROM runs ORDER BY created DESC') if json.loads(r[0]).get('task') == 'gepa-evolution'][:10]
        gepa_workspace = self.gepa.snapshot(cached_only=True)
        gepa_workspace.update(sdk=sdk, optimizer=optimizer)
        gepa_workspace.update(latestRun=self.decorate(gepa_runs[0]) if gepa_runs else None, runs=[{'id':r['id'],'status':r['status'],'createdAt':r['createdAt']} for r in gepa_runs])
        return {'schemaVersion': 1, 'mode': 'native-tools', 'serviceId': self.service_id, 'serverTime': now(), 'latestRun': self.decorate(runs[0]) if runs else None, 'runs': [{'id': r['id'], 'status': r['status'], 'task': r.get('task', 'project-health'), 'createdAt': r['createdAt']} for r in runs], 'skills': workspace, 'llm': llm_workspace, 'repair': repair_workspace, 'gepa': gepa_workspace,
                'challenges':self.challenges.summary(),
                'provider': {'revision': self.ollama.state()['revision'], 'config': self.ollama.state()['config'], 'busy': self.ollama.operation.locked(), 'warmup': self.ollama.warmup_status()}}

    def _submission(self, request_id, task, submission_hash):
        """Check admission/idempotency while the caller holds self.lock."""
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
        return None

    def start(self, registry, request_id, task='project-health', options=None):
        agents = validate_bindings(registry)
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
            raise ValueError('Invalid idempotency request ID')
        if task not in ('project-health', 'skill-evolution', 'llm-evolution', 'nanobot-repair', 'gepa-evolution') or (task == 'project-health' and options is not None):
            raise ValueError('Unsupported fixed workflow')
        submission_hash = hashlib.sha256(json.dumps({'agents': agents, 'task': task, 'options': options}, sort_keys=True).encode()).hexdigest()
        native_plan = None
        if task == 'project-health' and self.native_checks:
            with self.lock:
                existing = self._submission(request_id, task, submission_hash)
                if existing is not None:
                    return existing
            from native_check_plan import build
            native_plan = build(ROOT)
        prepared = None
        if task in ('nanobot-repair', 'gepa-evolution'):
            with self.lock:
                existing = self._submission(request_id, task, submission_hash)
                if existing is not None:
                    return existing
            # Cold or expired SDK imports must not hold the workflow mutex.
            # No run/model slot is allocated until admission is rechecked below.
            prepared = self.repair.freeze(options) if task == 'nanobot-repair' else self.gepa.freeze(options)
        with self.lock:
            existing = self._submission(request_id, task, submission_hash)
            if existing is not None:
                return existing
            config = self.skills.freeze(options) if task == 'skill-evolution' else self.llm.freeze(options) if task == 'llm-evolution' else prepared
            if task == 'gepa-evolution':
                self.gepa.check_revision(options['expectedRevision'])
                if config['profile']=='bank':self.challenges.check_revision(config['datasetSnapshot']['revision'])
            from skill_agents import TASKS as SKILL_TASKS
            from llm_engine import TASKS as LLM_TASKS
            from repair_engine import TASKS as REPAIR_TASKS
            from gepa_engine import TASKS as GEPA_TASKS
            tasks = GEPA_TASKS if task == 'gepa-evolution' else REPAIR_TASKS if task == 'nanobot-repair' else LLM_TASKS if task == 'llm-evolution' else SKILL_TASKS if config else TASKS
            if task in MODEL_TASKS:
                if not self.ollama.operation.acquire(blocking=False):
                    raise RuntimeError('An Ollama request is already running; wait first')
                agents.sort(key=lambda a: ('coordinator', 'worker', 'reflector', 'evaluator', 'reviewer').index(a['role']))
            try:
                if task in MODEL_TASKS and config['provider']['revision'] != self.ollama.state()['revision']:
                    raise RuntimeError('Provider settings changed; refresh first')
                identifier = 'RUN-' + str(uuid.uuid4())
                directory = self.local / 'runs' / identifier
                directory.mkdir(parents=True)
                if task=='gepa-evolution':config['runId']=identifier
                if native_plan is not None:
                    (directory/'native-check-plan.json').write_text(json.dumps(native_plan, indent=2))
                (directory / 'agents.json').write_text(json.dumps(agents, indent=2))
                if config:
                    (directory / ('gepa-config.json' if task == 'gepa-evolution' else 'repair-config.json' if task == 'nanobot-repair' else 'llm-config.json' if task == 'llm-evolution' else 'skill-config.json')).write_text(json.dumps(config, indent=2, ensure_ascii=False))
                timestamp = now()
                self.current = {'id': identifier, 'requestId': request_id, 'submissionHash': submission_hash, 'task': task, 'mode': 'native-tools', 'status': 'queued', 'createdAt': timestamp, 'updatedAt': timestamp, 'endedAt': None, 'checksPassed': None, 'agents': [{**a, 'adapter': 'gepa-nanobot-sdk-role' if task == 'gepa-evolution' else 'nanobot-sdk-role' if task == 'nanobot-repair' else 'ollama-skill-role' if task == 'llm-evolution' else 'native-tool-agent', 'status': 'queued', 'task': tasks[a['role']], 'pid': None, 'processAlive': False, 'startedAt': None, 'endedAt': None, 'updatedAt': timestamp, 'exitCode': None, 'error': None, 'logTail': ''} for a in agents], 'events': [], 'artifacts': []}
                if native_plan is not None:
                    self.current['nativeCheckPlan'] = native_plan
                if config:
                    self.current['gepaConfig' if task == 'gepa-evolution' else 'repairConfig' if task == 'nanobot-repair' else 'llmConfig' if task == 'llm-evolution' else 'skillConfig'] = config
                self.event(None, f'Queued actual {task} workflow; ' + ('real GEPA and nanobot SDK calls' if task=='gepa-evolution' else 'explicit model calls, no GEPA adapter' if task in MODEL_TASKS else 'no LLM or GEPA calls'))
                self.persist()
                self.cancel_event.clear()
                self.completion_event = threading.Event()
                self.thread = threading.Thread(target=self.execute, args=(directory,), daemon=True)
                self.thread.start()
                return copy.deepcopy(self.current)
            except Exception:
                if task in MODEL_TASKS:
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
                process.wait(timeout=ROLE_CLEANUP_SECONDS if self.current and self.current.get('nativeCheckPlan') else 2)
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
        completion = self.completion_event
        provider_leased = self.current.get('task') in MODEL_TASKS
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
                from step_trace import Step
                step=Step(self.logs,'runtime','role.process',directory.name,role=agent['role'])
                with self.lock:
                    agent.update(status='running', startedAt=now(), updatedAt=now())
                    self.event(agent, 'Starting: ' + agent['task'])
                    self.persist()
                try:
                    with log.open('w') as stream:
                        with self.lock:
                            if self.cancel_event.is_set():
                                step.finish('cancelled','Cancelled before process dispatch')
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
                            elif (self.current.get('task') in MODEL_TASKS and time.monotonic() - workflow_started > (self.current.get('llmConfig') or self.current.get('repairConfig') or self.current['gepaConfig'])['maxSeconds']) or (self.current.get('task') not in MODEL_TASKS and time.monotonic() - started > self.current.get('nativeCheckPlan', {}).get('roleMaximumSeconds', {}).get(agent['role'], self.stage_timeout)):
                                timed_out = True
                                timeout_error = 'Workflow time limit exceeded' if provider_leased else 'Stage timed out'
                                self.stop_process()
                            elif provider_leased:
                                observed = self.decorate(copy.deepcopy(self.current))
                                call = (observed.get('llmProgress') or observed.get('repairProgress') or observed.get('gepaProgress', {})).get('lastCall')
                                if call and call.get('status') == 'running' and call.get('deadlineEpoch', float('inf')) <= time.time():
                                    timed_out = True
                                    timeout_error = f'Model call #{call["id"]} exceeded its {call["timeoutSeconds"]}s time limit; no further requests were sent'
                                    self.stop_process()
                            tail = self.tail(log)
                            with self.lock:
                                agent.update(updatedAt=now(), processAlive=self.process.poll() is None, logTail=tail)
                                self.persist()
                            log_offset = self.capture_log(agent, log, log_offset)
                        code = self.process.wait()
                    tail = self.tail(log)
                    self.capture_log(agent, log, log_offset)
                    with self.lock:
                        error = timeout_error if timed_out else (tail.strip().splitlines()[-1][:1500] if tail.strip() else 'Process exited with an error') if code and not self.cancel_event.is_set() else None
                        agent.update(status='cancelled' if self.cancel_event.is_set() else 'failed' if timed_out or code else 'completed', exitCode=code, processAlive=False, endedAt=now(), updatedAt=now(), logTail=tail, error=error)
                        if provider_leased and agent['status'] in ('failed', 'cancelled'):
                            self.close_model_call(directory, agent['status'], error or 'Cancelled by user; no further requests were sent')
                        self.event(agent, f"{agent['status']}; PID {agent['pid']}; exit {code}")
                        step.finish(agent['status'],error)
                        self.process = None
                        self.persist()
                    if agent['status'] != 'completed':
                        break
                except Exception as exc:
                    step.finish('failed',str(exc))
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
                    if self.current.get('task') in ('skill-evolution', 'llm-evolution', 'nanobot-repair', 'gepa-evolution'):
                        self.current['gepaResult' if self.current['task'] == 'gepa-evolution' else 'repairResult' if self.current['task'] == 'nanobot-repair' else 'llmResult' if self.current['task'] == 'llm-evolution' else 'skillResult'] = result
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
            try:
                if provider_leased:
                    self.ollama.operation.release()
            finally:
                completion.set()

    @staticmethod
    def tail(path):
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 8192))
            return stream.read(8192).decode(errors='replace')

    def capture_log(self, agent, path, offset):
        with path.open('rb') as stream:
            stream.seek(offset); data = stream.read(65536); offset += len(data)
        records=[]
        for line in data.decode(errors='replace').splitlines():
            if line.strip():
                records.append({'module':agent['role'],
                    'level':'ERROR' if line.startswith(('Traceback','ValueError:','TimeoutError:','RuntimeError:')) else 'DEBUG',
                    'message':line,'run_id':self.current['id'],
                    'details':{'source':'subprocess','artifact':path.name,'truncated':len(line)>2048}})
        from debug_log import BATCH_LIMIT
        for start in range(0,len(records),BATCH_LIMIT):
            self.logs.append_many(records[start:start+BATCH_LIMIT])
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
        self.logs.close()
        fcntl.flock(self.lock_file, fcntl.LOCK_UN)
        self.lock_file.close()
