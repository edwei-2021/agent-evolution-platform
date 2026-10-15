"""Bounded process-safe diagnostic sidecars; never dispatch work or record bodies."""
from datetime import datetime, timezone
import fcntl
import http.client
import json
import os
import re
from pathlib import Path
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit, urlunsplit

CATEGORIES = ('startup', 'http', 'sdk', 'ollama', 'warmup', 'model-calls', 'workflows', 'status', 'errors')
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 2
ROOT = Path(__file__).resolve().parents[1]


def bodyless(value):
    if isinstance(value, dict):return {k:bodyless(v) for k,v in value.items()}
    if isinstance(value, list):return [bodyless(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(Ollama HTTP \d+):[^\n]*',r'\1 [server body omitted]',value)
        value = re.sub(r'Invalid Ollama response:[^\n]*','Invalid Ollama response [body omitted]',value)
    return value


def safe_url(value):
    parts = urlsplit(value)
    host = parts.hostname or ''
    if ':' in host:
        host = '[' + host + ']'
    return urlunsplit((parts.scheme, host + (':' + str(parts.port) if parts.port else ''), parts.path, '', ''))


def exception_details(exc, phase=None):
    reason = getattr(exc, 'reason', exc)
    from debug_log import redact
    return {'exceptionType': type(exc).__name__, 'reasonType': type(reason).__name__,
            'errno': getattr(reason, 'errno', None), 'httpStatus': getattr(exc, 'code', None),
            'phase': phase, 'error': redact(str(exc))[:1000],
            'frames': [{'file':f.filename,'line':f.lineno,'function':f.name}
                       for f in traceback.extract_tb(getattr(exc,'__traceback__',None))[-8:]]}


class DiagnosticLog:
    def __init__(self, root=None, *, maximum=MAX_BYTES, backups=BACKUPS):
        self.root = Path(root or os.environ.get('AEP_DIAGNOSTIC_ROOT', ROOT)).resolve()
        self.directory = self.root/'.local/diagnostics'
        self.maximum, self.backups = maximum, backups
        self._observed = None
        self._lock = threading.Lock()

    def write(self, category, event, *, level='INFO', correlation_id=None, **details):
        if category not in CATEGORIES:
            return False
        try:
            from debug_log import safe_details
            row = {'at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
                   'thread': threading.current_thread().name,
                   'sessionId': os.environ.get('AEP_DIAGNOSTIC_SESSION'),
                   'category': category, 'level': level, 'event': event,
                   'correlationId': correlation_id, 'details': bodyless(safe_details(details))}
            encoded = (json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode()
            if len(encoded) > 8192:
                row['details'] = {'truncated': True}
                encoded = (json.dumps(row) + '\n').encode()
            self.directory.mkdir(parents=True, exist_ok=True)
            # Each process opens its own lock. Hold it only for rotation/append,
            # never network, SQLite, fsync, model work or authoritative state.
            with (self.directory/(category+'.lock')).open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                path = self.directory/(category+'.jsonl')
                if path.exists() and path.stat().st_size + len(encoded) > self.maximum:
                    for index in range(self.backups, 0, -1):
                        old = path if index == 1 else self.directory/(category+f'.jsonl.{index-1}')
                        target = self.directory/(category+f'.jsonl.{index}')
                        if old.exists():
                            old.replace(target)
                with path.open('ab') as output:
                    output.write(encoded)
            if level == 'ERROR' and category != 'errors':
                self.write('errors', event, level=level, correlation_id=correlation_id,
                           sourceCategory=category, **details)
            return True
        except (OSError, ValueError, TypeError):
            return False

    def mirror(self, records):
        for row in records:
            module, message = row['module'], str(row['message'])
            metadata = row.get('details') or {}
            if not isinstance(metadata,dict):metadata={'value':metadata}
            if metadata.get('source') == 'subprocess':
                # Full role output already has its own local run artifact. Do
                # not copy prompts/answers/code from SDK stdout into support.
                self.write('workflows', 'role.output_observed', correlation_id=row.get('run_id'),
                           module=module, metadata=metadata, sourceLevel=row['level'])
                continue
            step = str(metadata.get('step', ''))
            if module == 'api':
                category = 'http'
            elif message.startswith('Model preload'):
                category = 'warmup'
            elif module == 'ollama':
                category = 'ollama'
            elif 'model.call' in step or 'Model call #' in message:
                category = 'model-calls'
            elif module == 'gui':
                category = 'startup'
            else:
                category = 'workflows'
            self.write(category, message, level=row['level'], correlation_id=row.get('run_id'),
                       module=module, metadata=metadata)

    def observe(self, snapshot):
        run = snapshot.get('latestRun') or {}
        warmup = snapshot.get('provider', {}).get('warmup') or {}
        config = run.get('repairConfig') or run.get('gepaConfig') or run.get('llmConfig') or {}
        state = {'runId': run.get('id'), 'status': run.get('status'), 'task': run.get('task'),
                 'createdAt': run.get('createdAt'), 'updatedAt': run.get('updatedAt'),
                 'error': run.get('error'), 'agents': [{k: a.get(k) for k in
                 ('id', 'role', 'status', 'pid', 'processAlive', 'exitCode', 'error')} for a in run.get('agents', [])],
                 'providerBusy': snapshot.get('provider', {}).get('busy'),
                 'frozenCodeHashes': config.get('provenance',{}).get('codeHashes',{}),
                 'limits': {k:config.get(k) for k in ('callBudget','maxSeconds','callTimeoutSeconds')},
                 'sdk': {'nanobot': {k:snapshot.get('repair',{}).get('sdk',{}).get(k) for k in ('available','version','errorCode')},
                         'gepa': {k:snapshot.get('gepa',{}).get('optimizer',{}).get(k) for k in ('available','version','errorCode')}},
                 'warmup': {k: warmup.get(k) for k in ('id', 'status', 'startedAt', 'finishedAt', 'error', 'phase')}}
        key = json.dumps(state, sort_keys=True)
        with self._lock:
            if key == self._observed:
                return
            self._observed = key
        self.write('status', 'state.observed', correlation_id=run.get('id'), **state)


class TransportTrace:
    def __init__(self, root=None, *, category='model-calls', correlation_id=None):
        self.logs = DiagnosticLog(root)
        self.category, self.correlation_id = category, correlation_id
        self.phase = 'created'
        self.started = time.monotonic()
        self.failure = None
        self.status = None
        self.request_id = uuid.uuid4().hex

    def event(self, event, **details):
        self.phase = event
        self.logs.write(self.category, event, correlation_id=self.correlation_id,
                        requestId=self.request_id, elapsedMs=round((time.monotonic()-self.started)*1000, 3), **details)

    def failed(self, exc):
        if self.failure is None:
            self.failure = exception_details(exc, self.phase)
            self.logs.write(self.category, 'request.failed', level='ERROR',
                correlation_id=self.correlation_id, elapsedMs=round((time.monotonic()-self.started)*1000, 3),
                requestId=self.request_id, **self.failure)

    def opener(self):
        trace = self
        class Connection(http.client.HTTPConnection):
            def connect(self):
                trace.event('connect.started', host=self.host, port=self.port, socketTimeout=self.timeout,
                            proxyBypassed=True)
                try:
                    super().connect()
                except Exception as exc:
                    trace.failed(exc)
                    raise
                trace.event('connect.completed', peer=self.sock.getpeername())
            def getresponse(self):
                trace.event('response.waiting')
                try:
                    response = super().getresponse()
                except Exception as exc:
                    trace.failed(exc)
                    raise
                trace.status = response.status
                trace.event('response.headers', httpStatus=response.status,
                            contentType=response.headers.get_content_type())
                return response
        class Handler(urllib.request.HTTPHandler):
            def http_open(self, request):
                return self.do_open(Connection, request)
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), Handler())

    def first_data(self, **details):
        self.event('response.first_data', **details)

    def result(self):
        return {'phase': self.phase, 'httpStatus': self.status,
                'requestId': self.request_id,
                'elapsedMs': round((time.monotonic()-self.started)*1000, 3),
                **({'failure': self.failure} if self.failure else {})}
