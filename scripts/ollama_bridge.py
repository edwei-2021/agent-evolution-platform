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
from model_provider import STRATA_DEFAULTS, kind as provider_kind, validate_strata, freeze, headers, payload as provider_payload, environment_defaults

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
    if isinstance(value, dict) and value.get('provider') == 'strata':
        return validate_strata(value)
    if isinstance(value, dict) and value.get('provider') == 'ollama':
        value = {k: v for k, v in value.items() if k != 'provider'}
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
        self.warmup_process = None
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
        if provider_kind(config) == 'strata':
            return config['baseUrl'][:-3]
        host = config['host'] or gateway()
        return f'http://{host}:{config["port"]}'

    def frozen(self):
        with self.lock:
            state = self.state()
            return {'revision': state['revision'], 'kind': provider_kind(state['config']),
                    'config': freeze(state['config']), 'endpoint': self.endpoint(state['config'])}

    def snapshot(self):
        with self.lock:
            state = self.state()
            try:
                base, error = self.endpoint(state['config']), None
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                base, error = None, str(exc)
            latest = self.path.parent / 'latest.json'
            defaults = environment_defaults()
            return {'schemaVersion': 1, **state, 'kind': provider_kind(state['config']), 'nativeBaseUrl': base,
                    'profiles': {**{'ollama': dict(DEFAULTS), 'strata': defaults},
                                 **state.get('profiles', {}), provider_kind(state['config']): state['config']},
                    'strataDefaultsFromEnvironment': defaults != STRATA_DEFAULTS,
                    'credentialsReady': provider_kind(state['config']) != 'strata' or bool(os.environ.get(state['config']['apiKeyEnv'])),
                    'openaiBaseUrl': base + '/v1' if base else None,
                    'discoveryError': error, 'proxyBypass': True,
                    'historicalEvidence': json.loads(self.evidence_path.read_text()),
                    'latest': json.loads(latest.read_text()) if latest.exists() else None,
                    'warmup': self.warmup_status(),
                    'busy': self.operation.locked(), 'workerIntegrated': True}

    def save(self, config, revision):
        config = validate_config(config)
        with self.lock:
            if self.operation.locked():
                raise RuntimeError('A model operation is active; wait or cancel before changing provider settings')
            state = self.state()
            if type(revision) is not int or revision != state['revision']:
                raise RuntimeError('Ollama settings changed; reload before saving')
            profiles = {**state.get('profiles', {}), provider_kind(state['config']): state['config'], provider_kind(config): config}
            atomic_write(self.path, json.dumps({'revision': revision + 1, 'config': config, 'profiles': profiles}, indent=2) + '\n')
            self.logs.append('ollama', 'INFO', 'Saved provider settings', details={'revision': revision + 1,
                'provider': provider_kind(config), 'model': config['model']})
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
                job['config'] = freeze(job['config'])
                atomic_write(self.path.parent / 'warmup.json', json.dumps(job))
                self.warmup_cancel.clear()
                self.logs.append('ollama', 'INFO', 'Model preload started', job['id'],
                    {'model': job['config']['model'], 'timeoutSeconds': job['timeoutSeconds'], 'keepAliveMinutes': keep_alive_minutes})
                from diagnostic_log import DiagnosticLog
                DiagnosticLog(self.root).write('warmup', 'warmup.queued', correlation_id=job['id'],
                    endpoint=job['endpoint'], model=job['config']['model'], revision=revision,
                    timeoutSeconds=job['timeoutSeconds'], keepAliveMinutes=keep_alive_minutes,
                    preparation='Strata native load; generation not verified' if provider_kind(job['config']) == 'strata' else 'empty-prompt preload; generation not verified')
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
                from diagnostic_log import DiagnosticLog
                DiagnosticLog(self.root).write('warmup', 'warmup.cancel_requested', correlation_id=identifier,
                                              reason='operator_request')
                if not self.warmup_thread or not self.warmup_thread.is_alive(): raise RuntimeError('Preload is not owned by this service')
                self.warmup_cancel.set()
                self.logs.append('ollama', 'WARNING', 'Preload cancellation requested; no model unload request sent', identifier)
            return job

    def _warmup(self, job):
        directory = self.path.parent
        config_path, result_path = directory / (job['id'] + '-config.json'), directory / (job['id'] + '-result.json')
        process = None
        reader = None
        from diagnostic_log import DiagnosticLog
        diagnostics = DiagnosticLog(self.root)
        diagnostics.write('warmup', 'worker.starting', correlation_id=job['id'])
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
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                self.warmup_process = process
                def collect_output():
                    total = 0
                    while True:
                        chunk = process.stdout.read(1024)
                        if not chunk:break
                        if total < 65536:
                            diagnostics.write('warmup', 'worker.output', correlation_id=job['id'],
                                output=chunk.decode(errors='replace'), truncated=total+len(chunk)>65536)
                        total += len(chunk)
                reader = threading.Thread(target=collect_output, name='warmup-output', daemon=True)
                reader.start()
                job['pid'] = process.pid
                diagnostics.write('warmup', 'worker.started', correlation_id=job['id'], pid=process.pid)
                with self.lock: atomic_write(directory / 'warmup.json', json.dumps(job))
                next_progress = time.monotonic()+10
                while process.poll() is None:
                    if self.warmup_cancel.wait(.1):
                        stop(); job.update(status='CANCELLED', error='Local preload stopped; the provider may still be loading the dispatched request'); break
                    if time.monotonic() - started >= job['timeoutSeconds']:
                        stop(); job.update(status='FAIL', error=f'Model preload exceeded its {job["timeoutSeconds"]}s absolute limit; no retry sent'); break
                    if time.monotonic() >= next_progress:
                        diagnostics.write('warmup', 'worker.waiting', correlation_id=job['id'],
                            elapsedMs=round((time.monotonic()-started)*1000,3), pid=process.pid,
                            timeoutSeconds=job['timeoutSeconds'], processAlive=process.poll() is None)
                        next_progress = time.monotonic()+10
                if job['status'] == 'RUNNING':
                    result = json.loads(result_path.read_text()) if result_path.exists() else {'error': 'Preload worker ended without a result'}
                    if process.returncode or result.get('error'): job.update(status='FAIL', error=result.get('error', 'Preload worker failed'),
                        **({'transport': result['transport']} if 'transport' in result else {}))
                    else: job.update(status='PRELOAD_PASS', **result)
                reader.join(timeout=1)
                diagnostics.write('warmup', 'worker.exited', correlation_id=job['id'],
                    exitCode=process.returncode, outputReaderAlive=reader.is_alive())
        except Exception as exc:
            stop(); job.update(status='FAIL', error=str(exc))
        finally:
            try:
                if reader:reader.join(timeout=1)
                if process and process.stdout and (not reader or not reader.is_alive()):process.stdout.close()
                job.update(finishedAt=datetime.now(timezone.utc).isoformat(), elapsedMs=round((time.monotonic() - started) * 1000, 3))
                diagnostics.write('warmup', 'warmup.finished', correlation_id=job['id'],
                    level='ERROR' if job['status']=='FAIL' else 'WARNING' if job['status']=='CANCELLED' else 'INFO',
                    status=job['status'], elapsedMs=job['elapsedMs'], error=job.get('error'),
                    transport=job.get('transport'), timeoutSeconds=job['timeoutSeconds'],
                    processAlive=bool(process and process.poll() is None), generationVerified=False)
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
        if self.warmup_thread and self.warmup_thread.is_alive():
            from diagnostic_log import DiagnosticLog
            DiagnosticLog(self.root).write('warmup', 'warmup.cancel_requested',
                reason='service_shutdown', correlation_id=(self.warmup_status() or {}).get('id'))
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
        if provider_kind(state['config']) == 'strata':
            values = {'OPENAI_BASE_URL': base+'/v1', 'STRATA_MODEL': state['config']['model']}
        for key in ('NO_PROXY', 'no_proxy'):
            existing = [x.strip() for x in os.environ.get(key, '').split(',') if x.strip()]
            values[key] = ','.join(dict.fromkeys(existing + ['localhost', '127.0.0.1', host]))
        atomic_write(target, '# Generated client settings; no connectivity test was performed.\n' +
                     ''.join(f'export {key}={shlex.quote(value)}\n' for key, value in values.items()))

    def request(self, base, path, config, payload=None, *, trace=None):
        from diagnostic_log import TransportTrace, safe_url
        trace = trace or TransportTrace(self.root, category='ollama')
        from model_provider import protect_opener
        opener = protect_opener(trace.opener(), config)
        if payload is not None and path.endswith('/chat/completions'):
            payload = provider_payload(config, payload)
        req = urllib.request.Request(base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json', **headers(config)})
        timeout = config['inferenceTimeout'] if payload is not None else config['metadataTimeout']
        trace.event('request.started', endpoint=safe_url(base+path), timeoutSeconds=timeout,
                    method='POST' if payload is not None else 'GET', model=config.get('model'), proxyBypassed=True)
        try:
            with opener.open(req, timeout=timeout) as response:
                trace.event('response.reading')
                # Bound remote responses; never follow arbitrary large model output.
                raw = response.read(2_000_001)
                trace.first_data(bytes=len(raw))
                if len(raw) > 2_000_000:
                    raise ValueError('Ollama response exceeds 2 MB')
                data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            trace.failed(exc)
            if provider_kind(config) == 'strata':
                raise ValueError(f'Strata HTTP {exc.code}; response body omitted') from exc
            detail = exc.read(2048).decode(errors='replace')
            raise ValueError(f'Ollama HTTP {exc.code}: {detail}') from exc
        except Exception as exc:
            trace.failed(exc)
            raise
        if not isinstance(data, dict) or data.get('error'):
            trace.failed(ValueError('Invalid Ollama response'))
            raise ValueError('Invalid Strata response; body omitted' if provider_kind(config) == 'strata' else 'Invalid Ollama response: ' + str(data.get('error') if isinstance(data, dict) else data))
        trace.event('request.completed', done=data.get('done'), responseModel=data.get('model'),
                    loadDurationNs=data.get('load_duration'), totalDurationNs=data.get('total_duration'))
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
            record.update(revision=revision, config=config, endpoint=base, provider=provider_kind(config))
            self.logs.append('ollama', 'INFO', kind + ' request started', details={'revision': revision, 'model': config['model']})
            if kind == 'metadata':
                strata = provider_kind(config) == 'strata'
                version = self.request(base, '/v1/status' if strata else '/api/version', config)
                if strata and (version.get('service') != 'strata' or type(version.get('loaded')) is not bool):
                    raise ValueError('Malformed Strata status')
                tags = {'models': []} if strata else self.request(base, '/api/tags', config)
                models = self.request(base, '/v1/models', config)
                if (not strata and not isinstance(version.get('version'), str)) or not isinstance(tags.get('models'), list) or not isinstance(models.get('data'), list):
                    raise ValueError('Malformed Ollama version/model listing')
                if any(not isinstance(m, dict) or not isinstance(m.get('id'), str) for m in models['data']):
                    raise ValueError('Malformed OpenAI model IDs')
                if any(not isinstance(m, dict) or not isinstance(m.get('name', m.get('model')), str) for m in tags['models']):
                    raise ValueError('Malformed native model IDs')
                record.update(status='METADATA_ONLY_PASS', serverVersion=version.get('engine') if strata else version['version'],
                              modelIds=[m['id'] for m in models['data']], inferenceTested=False)
                if strata:
                    record['loaded'] = version.get('loaded')
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
