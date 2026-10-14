"""Windows Ollama provider: offline configuration, explicit requests, no proxy.

The user's metadata evidence is historical. Reading settings never probes a host.
No model pull, Windows configuration, firewall edit or automatic inference.
"""
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit
import urllib.error
import urllib.request

DEFAULTS = {'host': '', 'port': 11435, 'model': '', 'metadataTimeout': 10,
            'inferenceTimeout': 600, 'maxTokens': 256}


def gateway():
    if 'microsoft' not in platform.release().lower():
        raise ValueError('Automatic host discovery requires WSL. Set an explicit Windows IPv4 host.')
    routes = json.loads(subprocess.check_output(
        ['ip', '-j', '-4', 'route', 'show', 'default'], text=True, timeout=5))
    hosts = list(dict.fromkeys(r['gateway'] for r in routes if r.get('gateway')))
    if len(hosts) != 1:
        raise ValueError('Expected one WSL NAT gateway. Set an explicit host for custom routes.')
    return str(ipaddress.IPv4Address(hosts[0]))


def validate_config(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError('Invalid Ollama settings fields')
    host = value['host']
    if not isinstance(host, str):
        raise ValueError('host must be empty (automatic WSL gateway) or IPv4')
    if host:
        host = str(ipaddress.IPv4Address(host))
        if ipaddress.IPv4Address(host).is_unspecified or ipaddress.IPv4Address(host).is_multicast:
            raise ValueError('host must be a reachable unicast IPv4 address')
    for key, maximum in [('port', 65535), ('metadataTimeout', 120),
                         ('inferenceTimeout', 3600), ('maxTokens', 8192)]:
        if type(value[key]) is not int or not 1 <= value[key] <= maximum:
            raise ValueError(f'{key} must be an integer between 1 and {maximum}')
    model = value['model']
    if not isinstance(model, str) or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ValueError('model must be an exact model ID of at most 200 characters')
    return {**value, 'host': host, 'model': model.strip()}


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class OllamaBridge:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / '.local/ollama/settings.json'
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        from debug_log import DebugLog
        self.logs = DebugLog(self.root)
        self.warmup_thread = None
        self.warmup_cancel = threading.Event()
        self.closing = False
        self.evidence_path = Path(__file__).resolve().parents[1] / 'docs/verification/ollama-user-evidence.json'

    def state(self):
        if self.path.exists():
            value = json.loads(self.path.read_text())
            validate_config(value['config'])
            return value
        return {'revision': 0, 'config': dict(DEFAULTS)}

    def endpoint(self, config):
        host = config['host'] or gateway()
        return f'http://{host}:{config["port"]}'

    def snapshot(self):
        with self.lock:
            state = self.state()
            try:
                base, error = self.endpoint(state['config']), None
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                base, error = None, str(exc)
            latest = self.path.parent / 'latest.json'
            return {'schemaVersion': 1, **state, 'nativeBaseUrl': base,
                    'openaiBaseUrl': base + '/v1' if base else None,
                    'discoveryError': error, 'proxyBypass': True,
                    'historicalEvidence': json.loads(self.evidence_path.read_text()),
                    'latest': json.loads(latest.read_text()) if latest.exists() else None,
                    'warmup': self.warmup_status(),
                    'busy': self.operation.locked(), 'workerIntegrated': True}

    def save(self, config, revision):
        config = validate_config(config)
        with self.lock:
            state = self.state()
            if type(revision) is not int or revision != state['revision']:
                raise RuntimeError('Ollama settings changed; reload before saving')
            atomic_write(self.path, json.dumps({'revision': revision + 1, 'config': config}, indent=2) + '\n')
            self.logs.append('ollama', 'INFO', 'Saved provider settings', details={'revision': revision + 1, 'model': config['model'], 'port': config['port']})
            return self.snapshot()

    def warmup_status(self):
        # A terminal record and release of its provider slot are one observable
        # transition. Reads remain RUNNING while logging/cleanup is in progress.
        with self.lock:
            path = self.path.parent / 'warmup.json'
            if not path.exists(): return None
            value = json.loads(path.read_text())
            end = datetime.fromisoformat(value['finishedAt']).timestamp() if value.get('finishedAt') else time.time()
            value['elapsedSeconds'] = round(max(0, end - datetime.fromisoformat(value['startedAt']).timestamp()), 1)
            return value

    def recover_warmup(self):
        with self.lock:
            value = self.warmup_status()
            if value and value['status'] == 'RUNNING':
                value.update(status='INTERRUPTED', finishedAt=datetime.now(timezone.utc).isoformat(),
                    error='GUI service restarted; previous preload state is unconfirmed')
                atomic_write(self.path.parent / 'warmup.json', json.dumps(value))
                self.logs.append('ollama', 'WARNING', value['error'], value['id'])

    def start_warmup(self, revision, keep_alive_minutes=15):
        if type(keep_alive_minutes) is not int or not 1 <= keep_alive_minutes <= 60:
            raise ValueError('keepAliveMinutes must be an integer between 1 and 60')
        if not self.operation.acquire(blocking=False):
            raise RuntimeError('An Ollama request or model experiment is already running')
        try:
            with self.lock:
                state = self.state()
                if self.closing: raise RuntimeError('Provider service is stopping')
                if type(revision) is not int or revision != state['revision']: raise RuntimeError('Ollama settings changed; refresh first')
                if not state['config']['model']: raise ValueError('Select and save a model first')
                job = {'id': 'WARM-' + str(uuid.uuid4()), 'revision': revision, 'config': state['config'],
                    'endpoint': self.endpoint(state['config']), 'keepAliveMinutes': keep_alive_minutes,
                    'timeoutSeconds': state['config']['inferenceTimeout'],
                    'startedAt': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING'}
                atomic_write(self.path.parent / 'warmup.json', json.dumps(job))
                self.warmup_cancel.clear()
                self.logs.append('ollama', 'INFO', 'Model preload started', job['id'],
                    {'model': job['config']['model'], 'timeoutSeconds': job['timeoutSeconds'], 'keepAliveMinutes': keep_alive_minutes})
                self.warmup_thread = threading.Thread(target=self._warmup, args=(job,), daemon=True)
                self.warmup_thread.start()
                return self.warmup_status()
        except Exception:
            self.operation.release(); raise

    def cancel_warmup(self, identifier):
        with self.lock:
            job = self.warmup_status()
            if not job or job['id'] != identifier: raise KeyError('Model preload not found')
            if job['status'] == 'RUNNING':
                if not self.warmup_thread or not self.warmup_thread.is_alive(): raise RuntimeError('Preload is not owned by this service')
                self.warmup_cancel.set()
                self.logs.append('ollama', 'WARNING', 'Preload cancellation requested; no model unload request sent', identifier)
            return job

    def _warmup(self, job):
        directory = self.path.parent
        config_path, result_path = directory / (job['id'] + '-config.json'), directory / (job['id'] + '-result.json')
        process = None
        started = time.monotonic()
        def stop():
            if process and process.poll() is None:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait(timeout=1)
        try:
            atomic_write(config_path, json.dumps(job))
            if self.warmup_cancel.is_set():
                job.update(status='CANCELLED', error='Preload cancelled before dispatch')
            else:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('warmup_worker.py')), str(config_path), str(result_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                job['pid'] = process.pid
                with self.lock: atomic_write(directory / 'warmup.json', json.dumps(job))
                while process.poll() is None:
                    if self.warmup_cancel.wait(.1):
                        stop(); job.update(status='CANCELLED', error='Local preload stopped; Ollama may still be loading the dispatched request'); break
                    if time.monotonic() - started >= job['timeoutSeconds']:
                        stop(); job.update(status='FAIL', error=f'Model preload exceeded its {job["timeoutSeconds"]}s absolute limit; no retry sent'); break
                if job['status'] == 'RUNNING':
                    result = json.loads(result_path.read_text()) if result_path.exists() else {'error': 'Preload worker ended without a result'}
                    if process.returncode or result.get('error'): job.update(status='FAIL', error=result.get('error', 'Preload worker failed'))
                    else: job.update(status='PRELOAD_PASS', **result)
        except Exception as exc:
            stop(); job.update(status='FAIL', error=str(exc))
        finally:
            try:
                job.update(finishedAt=datetime.now(timezone.utc).isoformat(), elapsedMs=round((time.monotonic() - started) * 1000, 3))
                self.logs.append('ollama', 'INFO' if job['status'] == 'PRELOAD_PASS' else 'WARNING' if job['status'] == 'CANCELLED' else 'ERROR',
                    'Model preload ' + job['status'] + (': ' + job['error'] if job.get('error') else ''), job['id'],
                    {k: job[k] for k in ('elapsedMs','loadDurationMs','totalDurationMs','responseModel') if k in job})
            finally:
                try:
                    config_path.unlink(missing_ok=True); result_path.unlink(missing_ok=True)
                except OSError: pass
                finally:
                    with self.lock:
                        try: atomic_write(directory / 'warmup.json', json.dumps(job))
                        finally: self.operation.release()

    def close(self):
        with self.lock: self.closing = True; self.warmup_cancel.set()
        if self.warmup_thread: self.warmup_thread.join(timeout=3)

    def export_environment(self, target):
        with self.lock:
            state = self.state()
            base = self.endpoint(state['config'])
        host = urlsplit(base).hostname
        values = {'OLLAMA_HOST': base, 'OLLAMA_BASE_URL': base,
                  'OPENAI_BASE_URL': base + '/v1', 'OPENAI_API_KEY': 'ollama',
                  'OLLAMA_MODEL': state['config']['model']}
        for key in ('NO_PROXY', 'no_proxy'):
            existing = [x.strip() for x in os.environ.get(key, '').split(',') if x.strip()]
            values[key] = ','.join(dict.fromkeys(existing + ['localhost', '127.0.0.1', host]))
        atomic_write(target, '# Generated client settings; no connectivity test was performed.\n' +
                     ''.join(f'export {key}={shlex.quote(value)}\n' for key, value in values.items()))

    def request(self, base, path, config, payload=None):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        timeout = config['inferenceTimeout'] if payload is not None else config['metadataTimeout']
        try:
            with opener.open(req, timeout=timeout) as response:
                # Bound remote responses; never follow arbitrary large model output.
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('Ollama response exceeds 2 MB')
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode(errors='replace')
            raise ValueError(f'Ollama HTTP {exc.code}: {detail}') from exc
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError('Invalid Ollama response: ' + str(data.get('error') if isinstance(data, dict) else data))
        return data

    def run(self, kind, revision, prompt=None):
        if kind not in ('metadata', 'chat'):
            raise ValueError('Unknown Ollama operation')
        if not self.operation.acquire(blocking=False):
            raise RuntimeError('An Ollama request is already running; no second request was sent')
        started = time.monotonic()
        record = {'kind': kind, 'startedAt': datetime.now(timezone.utc).isoformat(), 'status': 'FAIL'}
        try:
            with self.lock:
                state = self.state()
                if type(revision) is not int or revision != state['revision']:
                    raise RuntimeError('Ollama settings changed; reload before requesting')
            config = state['config']
            if kind == 'chat' and (not config['model'] or not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000):
                raise ValueError('Select a model and supply a prompt of 1..4000 characters')
            base = self.endpoint(config)
            record.update(revision=revision, config=config, endpoint=base)
            self.logs.append('ollama', 'INFO', kind + ' request started', details={'revision': revision, 'model': config['model']})
            if kind == 'metadata':
                version = self.request(base, '/api/version', config)
                tags = self.request(base, '/api/tags', config)
                models = self.request(base, '/v1/models', config)
                if not isinstance(version.get('version'), str) or not isinstance(tags.get('models'), list) or not isinstance(models.get('data'), list):
                    raise ValueError('Malformed Ollama version/model listing')
                if any(not isinstance(m, dict) or not isinstance(m.get('id'), str) for m in models['data']):
                    raise ValueError('Malformed OpenAI model IDs')
                if any(not isinstance(m, dict) or not isinstance(m.get('name', m.get('model')), str) for m in tags['models']):
                    raise ValueError('Malformed native model IDs')
                record.update(status='METADATA_ONLY_PASS', serverVersion=version['version'],
                              modelIds=[m['id'] for m in models['data']], inferenceTested=False)
            else:
                reply = self.request(base, '/v1/chat/completions', config, {
                    'model': config['model'], 'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False, 'temperature': 0, 'max_tokens': config['maxTokens']})
                try:
                    content = reply['choices'][0]['message']['content']
                except (KeyError, IndexError, TypeError) as exc:
                    raise ValueError('Malformed chat completion') from exc
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('No visible answer; inspect model output/token budget')
                record.update(status='INFERENCE_PASS', inferenceTested=True, prompt=prompt,
                              content=content, usage=reply.get('usage'), responseModel=reply.get('model'))
        except RuntimeError:
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            record['error'] = str(exc)
        finally:
            try:
                if 'config' in record:
                    record['elapsedMs'] = round((time.monotonic() - started) * 1000, 3)
                    record['finishedAt'] = datetime.now(timezone.utc).isoformat()
                    name = 'request-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json'
                    record['reportPath'] = '.local/ollama/' + name
                    with self.lock:
                        atomic_write(self.path.parent / name, json.dumps(record, ensure_ascii=False, indent=2) + '\n')
                        atomic_write(self.path.parent / 'latest.json', json.dumps(record, ensure_ascii=False, indent=2) + '\n')
                        self.logs.append('ollama', 'ERROR' if record['status'] == 'FAIL' else 'INFO', kind + ' ' + record['status'] + (': ' + record['error'] if record.get('error') else ''), details={'elapsedMs': record['elapsedMs'], 'model': config['model']})
            finally:
                self.operation.release()
        if 'config' not in record:
            raise ValueError(record.get('error', 'Ollama operation failed before dispatch'))
        return record
