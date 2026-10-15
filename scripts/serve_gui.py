#!/usr/bin/env python3
"""Serve only the public dist directory, without traversing external symlinks."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hmac
import json
import re
import sys
import tempfile
import time
import os
import platform
import subprocess
import uuid
from urllib.parse import urlsplit, parse_qs

DIST = Path(__file__).resolve().parents[1] / 'dist'
DEFAULT_PORT = 8765


class DiagnosticServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        from diagnostic_log import DiagnosticLog, exception_details
        exc = sys.exc_info()[1]
        runtime = getattr(self,'runtime',None)
        DiagnosticLog(runtime.root if runtime else DIST.parent).write('http','request.unhandled',
            level='ERROR',client=client_address[0],**exception_details(exc))
        super().handle_error(request,client_address)


def ollama_bridge(runtime):
    from ollama_bridge import OllamaBridge
    with runtime.lock:
        if not hasattr(runtime, 'ollama'):
            runtime.ollama = OllamaBridge(runtime.root)
        return runtime.ollama


class GuiHandler(SimpleHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        from diagnostic_log import DiagnosticLog
        runtime = getattr(self.server,'runtime',None)
        DiagnosticLog(runtime.root if runtime else DIST.parent).write('http', 'http.access',
            level='ERROR' if isinstance(code,int) and code>=500 else 'WARNING' if isinstance(code,int) and code>=400 else 'INFO',
            method=self.command, path=urlsplit(self.path).path[:240], status=code, bytes=size,
            client=self.client_address[0])
        super().log_request(code,size)

    def json_response(self, status, data):
        runtime = getattr(self.server, 'runtime', None)
        path = urlsplit(self.path).path
        if runtime and path == '/api/v1/runtime' and status == 200:
            runtime.diagnostics.observe(data)
        if runtime and hasattr(runtime, 'logs') and path != '/api/v1/debug/logs' and (self.command == 'POST' or status >= 400):
            match = re.search(r'(?:RUN|WARM)-[A-Za-z0-9-]+', path)
            runtime.logs.append('api', 'ERROR' if status >= 500 else 'WARNING' if status >= 400 else 'INFO',
                f'{self.command} {path[:180]} → {status}', match[0] if match else data.get('id'),
                {'status': status, 'error': data.get('error')})
        step=getattr(self,'_api_step',None)
        if step:
            if step.run_id is None and isinstance(data.get('id'),str):step.run_id=data['id']
            step.finish('failed' if status>=400 else 'completed',data.get('error'))
        payload = json.dumps(data, ensure_ascii=False).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected. Do not enter do_GET's OSError handler and
            # try to send a second HTTP response on the same closed socket.
            self.close_connection = True

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
                sdk, optimizer = runtime.sdk_snapshot()
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
            elif path == '/api/v1/debug/support':
                from export_diagnostics import build_bundle
                payload = build_bundle(runtime.root)
                try:
                    self.send_response(200)
                    self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition','attachment; filename="diagnostics.zip"')
                    self.send_header('Content-Length',str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError):
                    self.close_connection = True
            elif path == '/api/v1/debug/logs':
                values = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(values) - {'module','level','runId','q','before','limit'} or any(len(v) != 1 for v in values.values()):
                    raise ValueError('Invalid log query parameters')
                get = lambda key, default='': values.get(key, [default])[0]
                self.json_response(200, runtime.logs.list(module=get('module'), level=get('level'), run_id=get('runId'), query=get('q'),
                    before=int(get('before')) if get('before') else None, limit=int(get('limit', '100'))))
            elif path == '/api/v1/llm/skills':
                self.json_response(200, runtime.snapshot()['llm'])
            elif match := re.fullmatch(r'/api/v1/debug/steps/(RUN-[A-Za-z0-9-]+)',path):
                from step_trace import snapshot
                self.json_response(200,snapshot(runtime,match[1]))
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
            from step_trace import Step
            match=re.search(r'(?:RUN|WARM)-[A-Za-z0-9-]+',path)
            self._api_step=Step(runtime.logs,'api','http.mutation',match[0] if match else None,route=path[:180])
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
    from diagnostic_log import DiagnosticLog, exception_details
    diagnostics = DiagnosticLog(DIST.parent)
    os.environ['AEP_DIAGNOSTIC_ROOT'] = str(DIST.parent)
    os.environ['AEP_DIAGNOSTIC_SESSION'] = uuid.uuid4().hex
    try:
        revision = subprocess.run(['git','rev-parse','HEAD'],cwd=DIST.parent,
                                  capture_output=True,text=True,timeout=2).stdout.strip()
    except (OSError,subprocess.TimeoutExpired):
        revision = None
    encoding_cache=Path(os.environ.get('TIKTOKEN_CACHE_DIR',str(DIST.parent/'.local/cache/tiktoken')))
    try:encoding_ready=(encoding_cache/'9b5ad71b2ce5302211f9c61530b329a4922fc6a4').is_file()
    except OSError:encoding_ready=None
    recorded=diagnostics.write('startup','service.starting',root=str(DIST.parent),cwd=str(Path.cwd()),
        python=sys.executable,pythonVersion=sys.version,platform=platform.platform(),
        port=args.port,staticOnly=args.static_only,revision=revision,tempDirectory=tempfile.gettempdir(),
        proxyEnvironmentPresent=any(os.environ.get(k) for k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')),
        encodingCachePath=str(encoding_cache),encodingCacheReady=encoding_ready)
    if not recorded:print('Diagnostic files unavailable; inspect workspace permissions and free space.',file=sys.stderr)
    try:
        server = DiagnosticServer(('127.0.0.1', args.port), partial(GuiHandler, directory=str(DIST)))
    except OSError as exc:
        diagnostics.write('startup','service.bind_failed',level='ERROR',port=args.port,**exception_details(exc))
        print(f'Cannot start GUI on port {args.port}: {exc}. Choose another port with --port <number>.', file=sys.stderr)
        return 1
    runtime = None
    if not args.static_only:
        from runtime_service import RuntimeService
        try:
            runtime = RuntimeService(DIST.parent)
            server.runtime = runtime
        except (RuntimeError, OSError) as exc:
            diagnostics.write('startup','runtime.start_failed',level='ERROR',**exception_details(exc))
            server.server_close()
            print(f'Cannot start local runtime: {exc}', file=sys.stderr)
            return 1
    print(f'nanobot GEPA MVP — GUI + local runtime\nWorkspace: {Path.cwd()}\nTemp: {tempfile.gettempdir()}\nOpen http://localhost:{args.port}\nRuntime: {"native tool agents" if runtime else "disabled"}\nOllama bridge: explicit requests only; default Windows port 11435.\nPress Ctrl+C to stop. Model requests require explicit submission; SDK discovery is separate from model inference.', flush=True)
    diagnostics.write('startup','service.ready',port=args.port,serviceId=runtime.service_id if runtime else None)
    print('Diagnostic logs: '+str(diagnostics.directory),flush=True)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if runtime:
                runtime.close()
            diagnostics.write('startup','service.stopped',serviceId=runtime.service_id if runtime else None)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        from diagnostic_log import DiagnosticLog, exception_details
        DiagnosticLog(DIST.parent).write('startup','process.unhandled',level='ERROR',**exception_details(exc))
        raise
