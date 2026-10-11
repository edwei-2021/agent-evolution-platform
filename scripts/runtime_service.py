"""Single local supervisor with SQLite snapshots and real subprocess telemetry."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
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
        self.command_factory = command_factory or (lambda role, path: [sys.executable, str(ROOT / 'scripts/native_agents.py'), '--role', role, '--run-dir', str(path)])
        self.stage_timeout = stage_timeout
        self.thread = None
        self.process = None
        self.cancel_event = threading.Event()
        self.current = None
        self.closed = False
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

    def get_run(self, identifier):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise KeyError('Run not found')
            return json.loads(row[0])

    def snapshot(self):
        with self.lock, self.connect() as db:
            runs = [json.loads(row[0]) for row in db.execute('SELECT data FROM runs ORDER BY created DESC LIMIT 10')]
        return {'schemaVersion': 1, 'mode': 'native-tools', 'serviceId': self.service_id, 'serverTime': now(), 'latestRun': runs[0] if runs else None, 'runs': [{'id': r['id'], 'status': r['status'], 'createdAt': r['createdAt']} for r in runs]}

    def start(self, registry, request_id):
        agents = validate_bindings(registry)
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
            raise ValueError('Invalid idempotency request ID')
        with self.lock:
            if self.closed:
                raise RuntimeError('Runtime service is stopping')
            with self.connect() as db:
                prior = db.execute('SELECT data FROM runs WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                return json.loads(prior[0])
            if self.current and self.current['status'] not in TERMINAL:
                raise RuntimeError('A workflow is already running; cancel or wait before starting another')
            identifier = 'RUN-' + str(uuid.uuid4())
            directory = self.local / 'runs' / identifier
            directory.mkdir(parents=True)
            (directory / 'agents.json').write_text(json.dumps(agents, indent=2))
            timestamp = now()
            self.current = {'id': identifier, 'requestId': request_id, 'task': 'project-health', 'mode': 'native-tools', 'status': 'queued', 'createdAt': timestamp, 'updatedAt': timestamp, 'endedAt': None, 'checksPassed': None, 'agents': [{**a, 'adapter': 'native-tool-agent', 'status': 'queued', 'task': TASKS[a['role']], 'pid': None, 'processAlive': False, 'startedAt': None, 'endedAt': None, 'updatedAt': timestamp, 'exitCode': None, 'error': None, 'logTail': ''} for a in agents], 'events': [], 'artifacts': []}
            self.event(None, 'Queued real project-health workflow; no LLM or GEPA calls')
            self.persist()
            self.cancel_event.clear()
            self.thread = threading.Thread(target=self.execute, args=(directory,), daemon=True)
            self.thread.start()
            return copy.deepcopy(self.current)

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
        try:
            with self.lock:
                self.current['status'] = 'running'
                self.persist()
            for agent in self.current['agents']:
                if self.cancel_event.is_set():
                    break
                log = directory / (agent['role'] + '.log')
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
                        while self.process.poll() is None:
                            if self.cancel_event.wait(0.25):
                                self.stop_process()
                            elif time.monotonic() - started > self.stage_timeout:
                                timed_out = True
                                self.stop_process()
                            with self.lock:
                                agent.update(updatedAt=now(), processAlive=self.process.poll() is None, logTail=self.tail(log))
                                self.persist()
                        code = self.process.wait()
                    with self.lock:
                        agent.update(status='cancelled' if self.cancel_event.is_set() else 'failed' if timed_out or code else 'completed', exitCode=code, processAlive=False, endedAt=now(), updatedAt=now(), logTail=self.tail(log), error='Stage timed out' if timed_out else 'Process exited with an error' if code and not self.cancel_event.is_set() else None)
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
                    self.current['checksPassed'] = json.loads(review.read_text())['checksPassed']
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

    @staticmethod
    def tail(path):
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 8192))
            return stream.read(8192).decode(errors='replace')

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
        fcntl.flock(self.lock_file, fcntl.LOCK_UN)
        self.lock_file.close()
