#!/usr/bin/env python3
"""Serve only the public dist directory, without traversing external symlinks."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hmac
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
from urllib.parse import urlsplit, parse_qs

DIST = Path(__file__).resolve().parents[1] / 'dist'
DEFAULT_PORT = 8765


def ollama_bridge(runtime):
    from ollama_bridge import OllamaBridge
    with runtime.lock:
        if not hasattr(runtime, 'ollama'):
            runtime.ollama = OllamaBridge(runtime.root)
        return runtime.ollama


class GuiHandler(SimpleHTTPRequestHandler):
    def json_response(self, status, data):
        runtime = getattr(self.server, 'runtime', None)
        path = urlsplit(self.path).path
        if runtime and hasattr(runtime, 'logs') and path != '/api/v1/debug/logs' and (self.command == 'POST' or status >= 400):
            match = re.search(r'(?:RUN|WARM)-[A-Za-z0-9-]+', path)
            runtime.logs.append('api', 'ERROR' if status >= 500 else 'WARNING' if status >= 400 else 'INFO',
                f'{self.command} {path[:180]} → {status}', match[0] if match else data.get('id'),
                {'status': status, 'error': data.get('error')})
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def api_context(self, mutate=False):
        runtime = getattr(self.server, 'runtime', None)
        if runtime is None:
            self.json_response(503, {'error': 'Local runtime service is unavailable'})
            return None
        try:
            host = urlsplit('http://' + self.headers.get('Host', ''))
            if host.hostname not in ('localhost', '127.0.0.1') or host.username or host.password or host.path or host.port is None:
                raise ValueError('Invalid local Host')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host'):
                raise ValueError('Cross-origin access is not allowed')
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                raise ValueError('Cross-site access is not allowed')
            if mutate and not hmac.compare_digest(self.headers.get('X-Lab-Token', ''), runtime.csrf_token):
                raise ValueError('Missing or invalid local session token')
        except ValueError as exc:
            self.json_response(403, {'error': str(exc)})
            return None
        return runtime

    def do_GET(self):
        path = urlsplit(self.path).path
        if not path.startswith('/api/'):
            return super().do_GET()
        runtime = self.api_context()
        if runtime is None:
            return
        try:
            if path == '/api/v1/runtime/capabilities':
                from setup_wsl import find_node
                from repair_runtime import sdk_status
                sdk = sdk_status(runtime.root)
                from gepa_runtime import gepa_status
                optimizer = gepa_status(runtime.root)
                self.json_response(200, {'schemaVersion': 1, 'mode': 'native-tools', 'serviceId': runtime.service_id, 'csrfToken': runtime.csrf_token, 'engine': 'native-tool-agent', 'skillEngine': 'local-rule-search-v1', 'nodeReady': bool(find_node()), 'nanobotInstalled': sdk['available'], 'nanobotSdkVersion': sdk['version'], 'pythonRepairAvailable': sdk['available'], 'gepaInstalled': optimizer['available'], 'gepaVersion': optimizer['version'], 'gepaWorkerAvailable': optimizer['available'], 'frameworkConnected': False, 'modelConnected': False, 'llmSkillEngine': 'ollama-prompt-reflection-v1', 'llmWorkerAvailable': True})
            elif path == '/api/v1/runtime':
                self.json_response(200, runtime.snapshot())
            elif path == '/api/v1/gepa':
                self.json_response(200, runtime.snapshot()['gepa'])
            elif path == '/api/v1/repair':
                self.json_response(200, runtime.snapshot()['repair'])
            elif path == '/api/v1/skills':
                self.json_response(200, runtime.snapshot()['skills'])
            elif path == '/api/v1/llm/ollama':
                self.json_response(200, ollama_bridge(runtime).snapshot())
            elif path == '/api/v1/debug/logs':
                values = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(values) - {'module','level','runId','q','before','limit'} or any(len(v) != 1 for v in values.values()):
                    raise ValueError('Invalid log query parameters')
                get = lambda key, default='': values.get(key, [default])[0]
                self.json_response(200, runtime.logs.list(module=get('module'), level=get('level'), run_id=get('runId'), query=get('q'),
                    before=int(get('before')) if get('before') else None, limit=int(get('limit', '100'))))
            elif path == '/api/v1/llm/skills':
                self.json_response(200, runtime.snapshot()['llm'])
            elif match := re.fullmatch(r'/api/v1/debug/runs/(RUN-[A-Za-z0-9-]+)/(coordinator|worker|reflector|evaluator|reviewer)', path):
                runtime.get_run(match[1])
                target = (runtime.local / 'runs' / match[1] / (match[2] + '.log')).resolve()
                if not target.is_relative_to((runtime.local / 'runs').resolve()) or not target.is_file():
                    raise KeyError('Role log is not available yet')
                with target.open('rb') as stream:
                    size = target.stat().st_size; stream.seek(max(0, size - 200000)); raw = stream.read(200000)
                self.json_response(200, {'runId': match[1], 'role': match[2], 'content': raw.decode(errors='replace'), 'truncated': size > 200000, 'totalBytes': size})
            elif match := re.fullmatch(r'/api/v1/runtime/runs/(RUN-[A-Za-z0-9-]+)', path):
                self.json_response(200, runtime.get_run(match[1]))
            elif match := re.fullmatch(r'/api/v1/runtime/runs/(RUN-[A-Za-z0-9-]+)/artifacts/([A-Za-z0-9_-]+\.(?:json|log|md|py|patch))', path):
                run = runtime.get_run(match[1])
                target = (runtime.local / 'runs' / match[1] / match[2]).resolve()
                if match[2] not in run['artifacts'] or not target.is_relative_to((runtime.local / 'runs').resolve()) or not target.is_file():
                    raise KeyError('Artifact not found')
                content = target.read_text(errors='replace')
                self.json_response(200, {'name': match[2], 'content': content[:200000], 'truncated': len(content) > 200000, 'totalChars': len(content)})
            else:
                self.json_response(404, {'error': 'API route not found'})
        except KeyError as exc:
            self.json_response(404, {'error': str(exc)})
        except (OSError, ValueError) as exc:
            self.json_response(400 if path == '/api/v1/debug/logs' and isinstance(exc, ValueError) else 503, {'error': str(exc)})

    def do_POST(self):
        runtime = self.api_context(mutate=True)
        if runtime is None:
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 128000 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('A JSON request body of at most 128 KB is required')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('JSON body must be an object')
            path = urlsplit(self.path).path
            if path == '/api/v1/runtime/runs':
                self.json_response(202, runtime.start(body.get('registry'), body.get('requestId')))
            elif path == '/api/v1/debug/logs':
                from debug_log import LEVELS
                if set(body) != {'level','message','page'} or body.get('level') not in LEVELS or not isinstance(body.get('message'), str) or not 1 <= len(body['message']) <= 2048 or not isinstance(body.get('page'), str) or len(body['page']) > 80:
                    raise ValueError('Invalid browser log record')
                with runtime.lock:
                    stamp = time.monotonic()
                    runtime.browser_log_times = [t for t in runtime.browser_log_times if stamp - t < 60]
                    if len(runtime.browser_log_times) >= 60:
                        self.json_response(429, {'error': 'Browser log rate limit reached'}); return
                    runtime.browser_log_times.append(stamp)
                    recorded = runtime.logs.append('gui', body['level'], body['message'], details={'page': body['page'], 'source': 'browser'})
                if not recorded:
                    self.json_response(503, {'error': 'Local debug journal write failed'}); return
                self.json_response(202, {'recorded': True})
            elif path == '/api/v1/llm/ollama/warmup':
                if set(body) - {'expectedRevision','keepAliveMinutes'}: raise ValueError('Invalid preload fields')
                self.json_response(202, ollama_bridge(runtime).start_warmup(body.get('expectedRevision'), body.get('keepAliveMinutes', 15)))
            elif match := re.fullmatch(r'/api/v1/llm/ollama/warmup/(WARM-[A-Za-z0-9-]+)/cancel', path):
                self.json_response(200, ollama_bridge(runtime).cancel_warmup(match[1]))
            elif path == '/api/v1/llm/ollama/settings':
                self.json_response(200, ollama_bridge(runtime).save(body.get('config'), body.get('expectedRevision')))
            elif path == '/api/v1/gepa/runs':
                fields={'registry','requestId','profile','maxSeconds','callTimeoutSeconds','taskCallBudget','metricBudget','proposalBudget','providerRevision','expectedRevision'}
                if set(body)!=fields:raise ValueError('Unexpected GEPA submission fields')
                self.json_response(202, runtime.start(body['registry'],body['requestId'],'gepa-evolution',{k:body[k] for k in fields-{'registry','requestId'}}))
            elif match := re.fullmatch(r'/api/v1/gepa/runs/(RUN-[A-Za-z0-9-]+)/approve',path):
                if set(body)!={'expectedRevision'}:raise ValueError('Unexpected approval fields')
                self.json_response(200,runtime.gepa.approve(match[1],body['expectedRevision']))
            elif match := re.fullmatch(r'/api/v1/gepa/versions/(GSV-[A-Za-z0-9-]+)/activate',path):
                if set(body)!={'expectedRevision'}:raise ValueError('Unexpected activation fields')
                self.json_response(200,runtime.gepa.activate(match[1],body['expectedRevision']))
            elif path == '/api/v1/repair/runs':
                if set(body)!={'registry','requestId','maxSeconds','callTimeoutSeconds','callBudget','providerRevision'}:raise ValueError('Unexpected repair submission fields')
                options = {key: body.get(key) for key in ('maxSeconds', 'callTimeoutSeconds', 'callBudget', 'providerRevision')}
                self.json_response(202, runtime.start(body.get('registry'), body.get('requestId'), 'nanobot-repair', options))
            elif path == '/api/v1/llm/skills/runs':
                options = {key: body.get(key) for key in ('profile', 'maxSeconds', 'expectedRevision', 'providerRevision')}
                if 'callTimeoutSeconds' in body:
                    options['callTimeoutSeconds'] = body['callTimeoutSeconds']
                self.json_response(202, runtime.start(body.get('registry'), body.get('requestId'), 'llm-evolution', options))
            elif match := re.fullmatch(r'/api/v1/llm/skills/runs/(RUN-[A-Za-z0-9-]+)/approve', path):
                self.json_response(200, runtime.llm.approve(match[1], body.get('expectedRevision')))
            elif match := re.fullmatch(r'/api/v1/llm/skills/versions/(LSV-[A-Za-z0-9-]+)/activate', path):
                self.json_response(200, runtime.llm.activate(match[1], body.get('expectedRevision')))
            elif path in ('/api/v1/llm/ollama/metadata', '/api/v1/llm/ollama/chat'):
                result = ollama_bridge(runtime).run(path.rsplit('/', 1)[-1], body.get('expectedRevision'), body.get('prompt'))
                self.json_response(200, result)
            elif path == '/api/v1/skills/runs':
                self.json_response(202, runtime.start(body.get('registry'), body.get('requestId'), task='skill-evolution', options={'maxCandidates': body.get('maxCandidates'), 'expectedRevision': body.get('expectedRevision')}))
            elif path == '/api/v1/skills/execute':
                from skill_engine import execute
                with runtime.lock:
                    runtime.skills.check_revision(body.get('expectedRevision'))
                    version = runtime.skills.snapshot()['active']
                    output = execute(version['skill'], body.get('text'))
                    self.json_response(200, {'versionId': version['id'], 'label': version['label'], 'skillHash': version['skill']['hash'], 'input': body['text'], 'output': output})
            elif match := re.fullmatch(r'/api/v1/skills/runs/(RUN-[A-Za-z0-9-]+)/approve', path):
                self.json_response(200, runtime.skills.approve(match[1], body.get('expectedRevision')))
            elif match := re.fullmatch(r'/api/v1/skills/versions/(SKV-[A-Za-z0-9-]+)/activate', path):
                self.json_response(200, runtime.skills.activate(match[1], body.get('expectedRevision')))
            elif match := re.fullmatch(r'/api/v1/runtime/runs/(RUN-[A-Za-z0-9-]+)/cancel', path):
                self.json_response(200, runtime.cancel(match[1]))
            else:
                self.json_response(404, {'error': 'API route not found'})
        except (ValueError, UnicodeDecodeError) as exc:
            self.json_response(400, {'error': str(exc)})
        except KeyError as exc:
            self.json_response(404, {'error': str(exc)})
        except RuntimeError as exc:
            self.json_response(409, {'error': str(exc)})
        except OSError as exc:
            self.json_response(503, {'error': str(exc)})

    def send_head(self):
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(Path(self.directory).resolve()):
            self.send_error(404)
            return None
        # Avoid public directory listings; ordinary static assets remain accessible.
        if target.is_dir():
            index = (target / 'index.html').resolve()
            if not index.is_relative_to(Path(self.directory).resolve()) or not index.is_file():
                self.send_error(404)
                return None
        return super().send_head()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Local GUI HTTP port')
    parser.add_argument('--static-only', action='store_true', help='Serve GUI without starting the local runtime service')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if sys.version_info < (3, 11):
        parser.error('Python 3.11+ required')
    if not (DIST / 'index.html').is_file():
        parser.error('dist/index.html is missing')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(GuiHandler, directory=str(DIST)))
    except OSError as exc:
        print(f'Cannot start GUI on port {args.port}: {exc}. Choose another port with --port <number>.', file=sys.stderr)
        return 1
    runtime = None
    if not args.static_only:
        from runtime_service import RuntimeService
        try:
            runtime = RuntimeService(DIST.parent)
            server.runtime = runtime
        except (RuntimeError, OSError) as exc:
            server.server_close()
            print(f'Cannot start local runtime: {exc}', file=sys.stderr)
            return 1
    print(f'nanobot GEPA MVP — GUI + local runtime\nWorkspace: {Path.cwd()}\nTemp: {tempfile.gettempdir()}\nOpen http://localhost:{args.port}\nRuntime: {"native tool agents" if runtime else "disabled"}\nOllama bridge: explicit requests only; default Windows port 11435.\nPress Ctrl+C to stop. LLM Skill runs call the saved model only after explicit submission; no startup probes or GEPA adapter.', flush=True)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if runtime:
                runtime.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
