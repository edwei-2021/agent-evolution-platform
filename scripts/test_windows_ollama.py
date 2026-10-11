#!/usr/bin/env python3
"""Standalone WSL2 -> Windows Ollama diagnostic (Python standard library only).

Usage:
  python3 test_windows_ollama.py --model qwen3-coder:30b
  python3 test_windows_ollama.py --host 172.22.160.1 --port 11435
  python3 test_windows_ollama.py --api-only

Default: test both native and OpenAI-compatible inference. No model pull,
server launch, firewall edit, environment edit, or third-party Python package.
Exit codes: 0=requested checks passed; 1=check failure; 2=arguments;
            3=report could not be saved; 130=interrupted.
API-only success verifies metadata access, not inference.
Sources: https://learn.microsoft.com/en-us/windows/wsl/networking
         https://docs.ollama.com/api/chat
         https://docs.ollama.com/api/ps
         https://docs.ollama.com/api/openai-compatibility
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def readable_bytes(value):
    if not isinstance(value, (int, float)):
        return 'N/A'
    return f'{value / (1024 ** 3):.3f} GiB ({value} bytes)'


class Diagnostic:
    def __init__(self, args):
        self.args = args
        self.started = time.monotonic()
        self.lines = []
        self.report = {
            'script_version': '1.0',
            'started_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'API_METADATA_ONLY' if args.api_only else 'NATIVE_AND_OPENAI_INFERENCE',
            'checks': [], 'environment': {}, 'endpoint': None,
        }
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.base = None

    def log(self, message=''):
        line = f'[{datetime.now().astimezone().isoformat(timespec="seconds")}] {message}'
        self.lines.append(line)
        print(line, flush=True)

    def value(self, label, value, limit=2400):
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        if len(text) > limit:
            text = text[:limit] + ' ... [truncated; full value in JSON report]'
        # Escape controls from remote responses so output cannot alter terminal state.
        text = ''.join(c if ord(c) >= 32 or c == '\t' else f'\\x{ord(c):02x}' for c in text)
        self.log(f'  {label}: {text}')

    def result(self, name, ok, required=True, **details):
        status = 'PASS' if ok else ('FAIL' if required else 'WARN')
        self.report['checks'].append({'name': name, 'status': status, 'required': required, **details})
        self.log(f'[{status}] {name}')

    def command(self, argv):
        try:
            process = subprocess.run(argv, capture_output=True, text=True, timeout=5)
            return {'command': argv, 'exit_code': process.returncode,
                    'stdout': process.stdout.strip(), 'stderr': process.stderr.strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'command': argv, 'error': str(exc)}

    def environment(self):
        self.log('Environment and routes（環境與路由）')
        env = self.report['environment']
        env.update({'kernel': platform.release(), 'python': platform.python_version(),
                    'platform': platform.platform(),
                    'is_wsl': 'microsoft' in platform.release().lower(),
                    'proxy_variables_present': [key for key in
                        ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')
                        if os.environ.get(key)],
                    'proxy_policy': 'Bypassed for every diagnostic HTTP request'})
        for key in ('kernel', 'python', 'is_wsl', 'proxy_variables_present', 'proxy_policy'):
            self.value(key, env[key])
        env['default_routes'] = self.command(['ip', '-j', '-4', 'route', 'show', 'default'])
        env['ipv4_interfaces'] = self.command(['ip', '-j', '-4', 'addr', 'show'])
        self.value('default routes', env['default_routes'].get('stdout', env['default_routes']))
        if self.args.host:
            host = str(ipaddress.IPv4Address(self.args.host))
            self.value('host selection', 'Explicit --host; Windows ownership is not independently verified')
        else:
            if not env['is_wsl']:
                raise ValueError('Automatic host detection requires WSL2. Use --host for an explicit IPv4 endpoint.')
            routes = json.loads(env['default_routes'].get('stdout') or '[]')
            gateways = list(dict.fromkeys(r['gateway'] for r in routes if r.get('gateway')))
            if len(gateways) != 1:
                raise ValueError('Expected one NAT gateway. Inspect ip -4 route show default; supply --host explicitly.')
            host = str(ipaddress.IPv4Address(gateways[0]))
            self.value('host selection', 'WSL IPv4 default gateway (Windows 10 NAT assumption)')
        self.base = f'http://{host}:{self.args.port}'
        self.report['endpoint'] = self.base
        env['route_to_host'] = self.command(['ip', '-4', 'route', 'get', host])
        self.value('route to host', env['route_to_host'].get('stdout', env['route_to_host']))
        self.value('native URL', self.base)
        self.value('OpenAI-compatible URL', self.base + '/v1')
        self.value('metadata socket timeout', f'{self.args.connect_timeout} seconds')
        self.value('inference socket timeout', f'{self.args.timeout} seconds')
        self.value('maximum output tokens', self.args.max_tokens)
        return host

    def tcp(self, host):
        started = time.monotonic()
        try:
            with socket.create_connection((host, self.args.port), timeout=self.args.connect_timeout) as connection:
                details = {'elapsed_ms': round((time.monotonic() - started) * 1000, 3),
                           'local_address': connection.getsockname(), 'peer_address': connection.getpeername()}
            self.result('TCP connection（TCP 連線）', True, **details)
            for key, value in details.items(): self.value(key, value)
            return True
        except OSError as exc:
            self.result('TCP connection（TCP 連線）', False, error=str(exc),
                        elapsed_ms=round((time.monotonic() - started) * 1000, 3))
            self.value('error', str(exc))
            return False

    def http(self, name, path, payload=None, required=True, inference=False, validate=None):
        method = 'POST' if payload is not None else 'GET'
        self.log(f'{method} {self.base}{path}')
        started = time.monotonic()
        details = {'method': method, 'path': path}

        def fetch():
            body = None if payload is None else json.dumps(payload).encode('utf-8')
            headers = {'Content-Type': 'application/json', 'User-Agent': 'WSL-Ollama-Diagnostic/1.0'}
            if path.startswith('/v1/'):
                headers['Authorization'] = 'Bearer ollama'
            request = urllib.request.Request(self.base + path, data=body, headers=headers)
            limit = 16 * 1024 * 1024
            with self.opener.open(request, timeout=self.args.timeout if inference else self.args.connect_timeout) as response:
                status = response.status
                response_headers = {k: response.headers.get(k) for k in ('Content-Type', 'Content-Length', 'Server', 'Date')}
                raw = response.read(limit + 1)
            if len(raw) > limit: raise ValueError('Response exceeds 16 MiB diagnostic limit.')
            return status, response_headers, raw

        try:
            if inference:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(fetch)
                    while True:
                        try:
                            status, response_headers, raw = future.result(timeout=10)
                            break
                        except concurrent.futures.TimeoutError:
                            if future.done(): raise
                            self.log(f'  Waiting for inference（等待推論）: {time.monotonic() - started:.1f}s')
            else:
                status, response_headers, raw = fetch()
            details.update(http_status=status, headers=response_headers,
                           elapsed_ms=round((time.monotonic() - started) * 1000, 3), response_bytes=len(raw))
            self.value('HTTP status', status)
            self.value('response headers', response_headers)
            self.value('elapsed_ms', details['elapsed_ms'])
            self.value('response bytes', len(raw))
            try:
                data = json.loads(raw)
            except (UnicodeError, json.JSONDecodeError):
                details['body_preview'] = raw[:2000].decode('utf-8', errors='replace')
                raise ValueError('Response is not valid JSON; endpoint may be a different service.')
            details['response'] = data
            if not isinstance(data, dict): raise ValueError('Expected a JSON object.')
            if data.get('error'): raise ValueError(str(data['error']))
            if validate: validate(data)
            self.result(name, True, required=required, **details)
            return data
        except urllib.error.HTTPError as exc:
            body = exc.read(8192).decode('utf-8', errors='replace')
            details.update(http_status=exc.code, error=str(exc), error_body=body)
            self.value('HTTP status', exc.code)
            self.value('server error body', body)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            details['error'] = str(exc)
            self.value('error', str(exc))
        details['elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
        self.result(name, False, required=required, **details)
        return None

    def active(self, name):
        def validate(data):
            if not isinstance(data.get('models'), list): raise ValueError('Missing running-model list.')
        data = self.http(name, '/api/ps', required=False, validate=validate)
        if data is not None:
            if not data['models']: self.value('loaded models', '(none)')
            for model in data['models']:
                self.value('loaded model', {'name': model.get('name', model.get('model')),
                    'size': readable_bytes(model.get('size')), 'size_vram': readable_bytes(model.get('size_vram')),
                    'context_length': model.get('context_length'), 'expires_at': model.get('expires_at')})

    def run(self):
        host = self.environment()
        if not self.tcp(host): return
        def version_valid(data):
            if not isinstance(data.get('version'), str): raise ValueError('Missing Ollama version string.')
        version = self.http('Ollama version', '/api/version', validate=version_valid)
        if version: self.value('server version', version['version'])
        def list_valid(key):
            def validate(data):
                if not isinstance(data.get(key), list) or not all(isinstance(item, dict) for item in data[key]):
                    raise ValueError(f'Missing or invalid {key} list.')
            return validate
        tags = self.http('Native model listing', '/api/tags', validate=list_valid('models'))
        models = self.http('OpenAI model listing', '/v1/models', validate=list_valid('data'))
        if tags is not None:
            self.value('installed model count', len(tags['models']))
            for entry in tags['models']:
                self.value('installed model', {'name': entry.get('name', entry.get('model')),
                    'size': readable_bytes(entry.get('size')), 'modified_at': entry.get('modified_at'),
                    'digest': entry.get('digest'), 'details': entry.get('details', {})})
        if models is not None: self.value('OpenAI model IDs', [entry.get('id') for entry in models['data']])
        self.active('Loaded models before inference')
        if self.args.api_only:
            self.log('[SKIP] Inference: --api-only. Model usability has not been tested.')
            return
        if version is None or tags is None or models is None:
            self.log('[SKIP] Inference: required metadata checks failed.')
            return
        local_models = [entry for entry in tags['models'] if entry.get('name', entry.get('model'))
                        and not entry.get('remote_host') and not entry.get('remote_model')
                        and not entry.get('name', entry.get('model', '')).endswith(':cloud')]
        selected = self.args.model
        if not selected and local_models:
            selected_entry = min(local_models, key=lambda entry: entry.get('size') if isinstance(entry.get('size'), (int,float)) else math.inf)
            selected = selected_entry.get('name', selected_entry.get('model'))
            self.value('automatic model selection', 'Smallest listed local model by stored size')
        eligible = [entry.get('name', entry.get('model')) for entry in local_models]
        compatible_ids = [entry.get('id') for entry in models['data']]
        if not selected or selected not in eligible or selected not in compatible_ids:
            self.result('Selected local model', False, requested_model=selected,
                        error='Exact local model ID must appear in both APIs. No model is pulled automatically.')
            return
        self.report['selected_model'] = selected
        self.result('Selected local model', True, model=selected)
        self.value('selected model', selected)
        show = self.http('Model details', '/api/show', {'model': selected}, required=False)
        if show:
            for key in ('details', 'capabilities', 'parameters'):
                self.value(key, show.get(key))
            info = show.get('model_info', {})
            if isinstance(info, dict):
                self.value('context metadata', {key: value for key, value in info.items() if 'context_length' in key})
            if show.get('remote_host') or show.get('remote_model'):
                self.result('Local inference requirement', False, error='Selected model is remote/cloud-backed; no inference requested.')
                return
        messages = [{'role': 'user', 'content': 'Reply with the word OK.'}]
        def native_valid(data):
            message = data.get('message', {})
            if data.get('done') is not True or not isinstance(message, dict): raise ValueError('Incomplete native chat response.')
            if not isinstance(message.get('content'), str) or not message['content'].strip():
                raise ValueError('No visible answer; inspect thinking output and increase --max-tokens if needed.')
        native = self.http('Native inference（原生 API 推論）', '/api/chat', {
            'model': selected, 'messages': messages, 'stream': False,
            'options': {'temperature': 0, 'num_predict': self.args.max_tokens}},
            inference=True, validate=native_valid)
        if native:
            self.value('native answer', native['message']['content'])
            for key in ('model', 'done_reason', 'prompt_eval_count', 'eval_count'):
                self.value(key, native.get(key))
            for key in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
                ns = native.get(key)
                self.value(key + '_seconds', round(ns / 1e9, 6) if isinstance(ns, (int, float)) else None)
            ns, count = native.get('eval_duration'), native.get('eval_count')
            if isinstance(ns, (int,float)) and ns > 0 and isinstance(count, (int,float)):
                self.value('generation tokens/sec', round(count / (ns / 1e9), 3))
        def compatible_valid(data):
            content = data['choices'][0]['message'].get('content')
            if not isinstance(content, str) or not content.strip():
                raise ValueError('No visible compatible chat answer; inspect response and output token budget.')
        compatible = self.http('OpenAI-compatible inference（相容 API 推論）', '/v1/chat/completions', {
            'model': selected, 'messages': messages, 'stream': False,
            'temperature': 0, 'max_tokens': self.args.max_tokens}, inference=True, validate=compatible_valid)
        if compatible:
            self.value('compatible answer', compatible['choices'][0]['message']['content'])
            self.value('finish_reason', compatible['choices'][0].get('finish_reason'))
            self.value('usage', compatible.get('usage'))
            self.value('response model', compatible.get('model'))
        self.active('Loaded models after inference')

    def finish(self, interrupted=False):
        failures = [item for item in self.report['checks'] if item['required'] and item['status'] == 'FAIL']
        code = 130 if interrupted else (1 if failures else 0)
        status = 'INTERRUPTED' if interrupted else ('FAIL' if failures else ('METADATA_ONLY_PASS' if self.args.api_only else 'FULL_PASS'))
        self.report.update(status=status, exit_code=code, elapsed_seconds=round(time.monotonic()-self.started, 3),
                           finished_at=datetime.now(timezone.utc).isoformat())
        self.log('Summary（檢查摘要）')
        for item in self.report['checks']:
            self.log(f"  {item['status']:4} {item['name']} ({'required' if item['required'] else 'optional'})")
        self.value('overall status', status)
        self.value('total elapsed seconds', self.report['elapsed_seconds'])
        self.value('exit code', code)
        if failures:
            self.log('Troubleshooting（排除方向）:')
            self.log('  TCP refused: check Windows Ollama listener, OLLAMA_HOST bind, gateway and port.')
            self.log('  TCP timeout: check current WSL IP, Windows firewall rule and VPN routing.')
            self.log('  HTTP errors: inspect the recorded status/body and exact installed model ID.')
            self.log('  Metadata PASS but inference FAIL: inspect Windows model loading, memory and server.log.')
            self.log('  First model loading can be slow. Retry with --timeout 1200 if appropriate.')
        if self.base:
            self.log('Client endpoint suggestions（客戶端位址；未修改環境）:')
            self.log('  export OLLAMA_HOST=' + shlex.quote(self.base))
            self.log('  export OPENAI_BASE_URL=' + shlex.quote(self.base + '/v1'))
            self.log('  export OPENAI_API_KEY=ollama')
        self.log('HTTP timings include client/network overhead. Native model timings come from the server.')
        self.log('Two inference calls are sequential; model loading/cache can make their timings differ.')
        folder = Path(self.args.out_dir).expanduser()
        prefix = 'ollama-test-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + f'-{os.getpid()}'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            text_path, json_path = folder / (prefix + '.log'), folder / (prefix + '.json')
            self.value('text report', str(text_path.resolve()))
            self.value('JSON report', str(json_path.resolve()))
            text_path.write_text('\n'.join(self.lines) + '\n', encoding='utf-8')
            json_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except OSError as exc:
            self.log(f'[FAIL] Could not save diagnostic reports: {exc}')
            return 3
        return code


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', help='Windows IPv4 override; default: WSL NAT gateway')
    parser.add_argument('--port', type=int, default=11435, help='Windows Ollama port (default: 11435; normal Ollama default: 11434)')
    parser.add_argument('--model', help='Exact local model ID; default: smallest installed local model')
    parser.add_argument('--api-only', action='store_true', help='Only test TCP and metadata APIs; skip inference')
    parser.add_argument('--connect-timeout', type=float, default=10, help='TCP/metadata socket timeout in seconds')
    parser.add_argument('--timeout', type=float, default=600, help='Inference socket timeout in seconds')
    parser.add_argument('--max-tokens', type=int, default=256, help='Maximum generated tokens per inference')
    parser.add_argument('--out-dir', default='./ollama-test-logs', help='Text/JSON report folder')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.max_tokens <= 0:
        parser.error('Port must be 1..65535 and --max-tokens must be positive.')
    if any(not math.isfinite(value) or value <= 0 for value in (args.connect_timeout, args.timeout)):
        parser.error('Timeouts must be positive finite values.')
    if args.host:
        try: ipaddress.IPv4Address(args.host)
        except ValueError: parser.error('--host must be an IPv4 address.')
    diagnostic = Diagnostic(args)
    interrupted = False
    try:
        diagnostic.run()
    except KeyboardInterrupt:
        interrupted = True
        diagnostic.log('[INTERRUPTED] User stopped the diagnostic.')
    except Exception as exc:
        diagnostic.result('Diagnostic execution', False, error=f'{type(exc).__name__}: {exc}')
        diagnostic.value('error', f'{type(exc).__name__}: {exc}')
    return diagnostic.finish(interrupted=interrupted)


if __name__ == '__main__':
    sys.exit(main())
