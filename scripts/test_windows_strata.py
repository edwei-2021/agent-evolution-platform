#!/usr/bin/env python3
"""Standalone Strata diagnostic (Python standard library only).

Default: metadata only at http://127.0.0.1:8081/v1. Explicit --stage chat,
tools or all enables bounded model requests. No retries, endpoint fallback,
model downloads, server setup, firewall edits or saved-provider changes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request
import uuid
import zipfile

MAX_BYTES = 2_000_000
STAGES = ('metadata', 'chat', 'tools', 'all')
SOURCE = 'https://github.com/edwei-2021/Strata/tree/61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406'


def emit(event, **details):
    print(json.dumps({'event': event, **details}, ensure_ascii=True), flush=True)


def decode_stream(response, notify):
    """The project's single-choice SSE/tool-delta contract; keep-alives aren't progress."""
    text, reasoning, tools, lines = '', 0, {}, []
    finish, model, total, chunks, first = None, None, 0, 0, True
    while True:
        raw = response.readline(65537)
        total += len(raw)
        if len(raw) > 65536 or total > MAX_BYTES:
            raise ValueError('SSE response exceeds size limit')
        if not raw:
            raise ValueError('SSE disconnected before [DONE]')
        line = raw.decode('utf-8').rstrip('\r\n')
        if line.startswith('data:'):
            lines.append(line[5:].lstrip(' '))
        elif not line and lines:
            data, lines = '\n'.join(lines), []
            if data == '[DONE]':
                if finish is None:
                    raise ValueError('SSE ended without finish_reason')
                message = {'role': 'assistant', 'content': text}
                if tools:
                    message['tool_calls'] = [tools[i] for i in sorted(tools)]
                return {'model': model, 'choices': [{'message': message, 'finish_reason': finish}]}, chunks
            item = json.loads(data)
            if not isinstance(item, dict) or item.get('error'):
                raise ValueError('SSE server error or malformed event; body omitted')
            choices = item.get('choices')
            if not isinstance(choices, list) or len(choices) > 1:
                raise ValueError('SSE requires a single choice')
            model = item.get('model', model)
            if choices:
                choice = choices[0]
                if not isinstance(choice, dict) or choice.get('index', 0) != 0:
                    raise ValueError('Invalid SSE choice index')
                delta = choice.get('delta')
                if not isinstance(delta, dict):
                    raise ValueError('Invalid SSE delta')
                content = delta.get('content', '')
                thought = delta.get('reasoning_content', delta.get('reasoning', ''))
                content = '' if content is None else content
                thought = '' if thought is None else thought
                if not isinstance(content, str) or not isinstance(thought, str):
                    raise ValueError('Invalid SSE text')
                text += content
                reasoning += len(thought)
                if len(text) > 12000 or reasoning > 200000:
                    raise ValueError('SSE text exceeds project limits')
                for part in delta.get('tool_calls') or []:
                    index = part.get('index')
                    if type(index) is not int or not 0 <= index < 8 or part.get('type', 'function') != 'function':
                        raise ValueError('Invalid streamed tool index/type')
                    tool = tools.setdefault(index, {'id': '', 'type': 'function',
                                                    'function': {'name': '', 'arguments': ''}})
                    fn = part.get('function', {})
                    if not isinstance(fn, dict):
                        raise ValueError('Invalid tool function delta')
                    for target, key, value, limit in [(tool, 'id', part.get('id', ''), 200),
                            (tool['function'], 'name', fn.get('name', ''), 100),
                            (tool['function'], 'arguments', fn.get('arguments', ''), 16000)]:
                        if not isinstance(value, str):
                            raise ValueError('Invalid tool string delta')
                        target[key] += value
                        if len(target[key]) > limit:
                            raise ValueError('Tool delta exceeds project limits')
                if choice.get('finish_reason') is not None:
                    finish = choice['finish_reason']
                    if not isinstance(finish, str) or not finish:
                        raise ValueError('Invalid finish_reason')
                if first and (content or thought or delta.get('tool_calls')):
                    notify('response.first_data')
                    first = False
            chunks += 1
            if chunks > 10000:
                raise ValueError('SSE exceeds event limit')


def worker():
    """One HTTP request. Parent enforces its absolute limit, even for trickle bodies."""
    request = json.loads(sys.stdin.read(200001))
    phase = 'request.started'

    def note(event, **details):
        nonlocal phase
        phase = event
        emit(event, **details)

    def connection(base):
        class Connection(base):
            def connect(self):
                note('connect.started', host=self.host, port=self.port)
                super().connect()
                note('connect.completed', peer=list(self.sock.getpeername()))
                self.sock.settimeout(request['timeout'])

            def getresponse(self):
                note('response.waiting')
                response = super().getresponse()
                note('response.headers', httpStatus=response.status,
                     contentType=response.headers.get_content_type())
                return response
        return Connection

    class HTTP(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(connection(http.client.HTTPConnection), req)

    class HTTPS(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(connection(http.client.HTTPSConnection), req, context=self._context)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    try:
        note('request.started', method='POST' if request['payload'] is not None else 'GET',
             url=request['url'], proxyBypassed=True)
        key = os.environ.get(request['keyEnv']) or 'strata-local'
        headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream, application/json',
                   'Authorization': 'Bearer ' + key, 'User-Agent': 'AEP-Strata-Diagnostic/1.0'}
        req = urllib.request.Request(request['url'], headers=headers,
            data=json.dumps(request['payload']).encode() if request['payload'] is not None else None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), HTTP(), HTTPS(), NoRedirect())
        with opener.open(req, timeout=request['connectTimeout']) as response:
            note('response.reading')
            fmt = response.headers.get_content_type()
            if fmt == 'text/event-stream' and request['payload'] is not None:
                result, chunks = decode_stream(response, note)
            else:
                if fmt != 'application/json':
                    raise ValueError('Expected application/json or requested SSE, received ' + fmt)
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('JSON response exceeds size limit')
                note('response.first_data', bytes=len(raw))
                result, chunks = json.loads(raw), 0
            if not isinstance(result, dict) or result.get('error'):
                raise ValueError('Server error or malformed JSON object; body omitted')
            note('request.completed', format=fmt, chunks=chunks)
            emit('result', data=result, format=fmt)
    except Exception as exc:
        reason = getattr(exc, 'reason', exc)
        message = ('HTTP ' + str(exc.code) + '; response body omitted'
                   if isinstance(exc, urllib.error.HTTPError) else str(reason))
        emit('failure', phase=phase, errorType=type(exc).__name__, reasonType=type(reason).__name__,
             errno=getattr(reason, 'errno', None), httpStatus=getattr(exc, 'code', None), error=message[:800])
        return 1
    return 0


def endpoint(args):
    if args.base_url:
        if args.port is not None:
            raise ValueError('--port requires --host; put the port in --base-url otherwise')
        base = args.base_url.rstrip('/')
        mode = 'explicit-base-url'
    elif args.host:
        host = args.host
        if host == 'auto':
            if 'microsoft' not in platform.release().lower():
                raise ValueError('--host auto requires WSL; use an explicit IPv4 address')
            routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default'],
                                                        text=True, timeout=5))
            hosts = list(dict.fromkeys(r['gateway'] for r in routes if r.get('gateway')))
            if len(hosts) != 1:
                raise ValueError('Expected one WSL gateway; use --host with the verified Windows IPv4')
            host = hosts[0]
        host = str(ipaddress.IPv4Address(host))
        base = f'http://{host}:{args.port or 8081}/v1'
        mode = 'explicit-gateway' if args.host == 'auto' else 'explicit-host'
    else:
        if args.port is not None:
            raise ValueError('--port requires --host')
        base, mode = 'http://127.0.0.1:8081/v1', 'provided-loopback-default'
    url = urlsplit(base)
    if url.scheme not in ('http', 'https') or url.username or url.password or '?' in base or '#' in base:
        raise ValueError('Use an HTTP(S) base URL without credentials, query or fragment')
    if not url.hostname or not url.path.endswith('/v1') or any(ord(c) < 33 for c in base):
        raise ValueError('Base URL must have a host and end in /v1')
    if url.hostname != 'localhost':
        address = ipaddress.ip_address(url.hostname)
        if address.is_unspecified or address.is_multicast:
            raise ValueError('Use a reachable unicast address, not a server bind address')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid base URL port')
    return base, mode


class Diagnostic:
    def __init__(self, args, base, selection):
        self.args, self.base = args, base
        self.secret = os.environ.get(args.api_key_env) or ''
        self.started = time.monotonic()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        self.directory = Path(args.out_dir) / ('STRATA-' + stamp)
        self.directory.mkdir(parents=True)
        self.report = {'schemaVersion': 1, 'startedAt': datetime.now(timezone.utc).isoformat(),
            'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'reviewedSource': SOURCE, 'baseUrl': base, 'endpointSelection': selection, 'stage': args.stage,
            'model': args.model, 'reasoningEffort': args.reasoning_effort, 'maxTokens': args.max_tokens,
            'connectTimeoutSeconds': args.connect_timeout, 'requestTimeoutSeconds': args.timeout,
            'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                'isWsl': 'microsoft' in platform.release().lower(), 'proxyBypassed': True,
                'authorization': 'environment' if self.secret else 'local-placeholder'},
            'requests': [], 'checks': [], 'modelRequests': 0, 'capabilities': {}}

    def clean(self, value):
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str) and self.secret:
            return value.replace(self.secret, '[REDACTED]')
        return value

    def log(self, event, **details):
        row = self.clean({'at': datetime.now(timezone.utc).isoformat(), 'event': event, **details})
        line = json.dumps(row, ensure_ascii=True)
        with (self.directory/'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
        print(line, flush=True)

    def request(self, step, path, payload=None, *, optional=False):
        timeout = self.args.timeout if payload is not None else self.args.metadata_timeout
        record = {'step': step, 'method': 'POST' if payload is not None else 'GET',
                  'url': self.base + path, 'phase': 'worker.starting', 'status': 'running'}
        self.report['requests'].append(record)
        self.report['modelRequests'] += int(payload is not None)
        started = time.monotonic()
        process = None
        reader = None
        events = queue.Queue()
        result, failure = None, None
        self.log('check.started', step=step, url=record['url'], absoluteLimitSeconds=timeout)
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--_worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8')
            record['workerPid'] = process.pid
            config = {'url': record['url'], 'payload': payload, 'timeout': timeout,
                      'connectTimeout': min(timeout, self.args.connect_timeout), 'keyEnv': self.args.api_key_env}
            process.stdin.write(json.dumps(config)); process.stdin.close()

            def collect():
                for line in process.stdout:
                    try:
                        events.put(json.loads(line))
                    except ValueError:
                        events.put({'event': 'failure', 'error': 'Invalid diagnostic worker output'})
                events.put(None)
            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            next_wait = time.monotonic() + 10
            while True:
                if time.monotonic() - started >= timeout:
                    raise TimeoutError('Absolute request limit exceeded; no retry sent')
                try:
                    event = events.get(timeout=min(.1, max(.001, timeout-(time.monotonic()-started))))
                except queue.Empty:
                    if time.monotonic() >= next_wait:
                        self.log('request.waiting', step=step, phase=record['phase'],
                                 elapsedSeconds=round(time.monotonic()-started, 1))
                        next_wait = time.monotonic() + 10
                    continue
                if event is None:
                    break
                kind = event.pop('event')
                if kind == 'result':
                    result = event
                elif kind == 'failure':
                    failure = event
                else:
                    record['phase'] = kind
                    if 'httpStatus' in event:
                        record['httpStatus'] = event['httpStatus']
                    self.log(kind, step=step, elapsedMs=round((time.monotonic()-started)*1000, 3), **event)
            if failure or result is None:
                record['failure'] = failure or {'error': 'Worker exited without a result'}
                raise ValueError(record['failure']['error'])
            record.update(status='passed', responseFormat=result['format'])
            return result['data']
        except BaseException as exc:
            record.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed',
                          error=f'{type(exc).__name__}: {exc}')
            self.log('check.failed', **record)
            if optional and isinstance(exc, Exception) and record.get('httpStatus') == 404:
                record['status'] = 'unsupported'
                return None
            raise
        finally:
            if process:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=1)
                if reader:
                    reader.join(timeout=1)
                process.stdout.close()
                if not process.stdin.closed:
                    process.stdin.close()
                record.update(workerExitCode=process.returncode, workerReaped=process.poll() is not None)
            record['elapsedMs'] = round((time.monotonic()-started)*1000, 3)

    def check(self, name, **details):
        self.report['checks'].append({'name': name, 'status': 'passed', **details})
        self.log('check.passed', name=name, **details)

    def payload(self, messages, *, tools=None, stream=False):
        value = {'model': self.args.model, 'messages': messages, 'stream': stream,
                 'temperature': 0, 'max_tokens': self.args.max_tokens}
        if self.args.reasoning_effort != 'default':
            value['reasoning_effort'] = self.args.reasoning_effort
        if tools is not None:
            value['tools'] = tools
        return value

    @staticmethod
    def message(reply):
        choices = reply.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError('Expected one chat completion choice')
        choice = choices[0]
        if choice.get('finish_reason') not in ('stop', 'tool_calls'):
            raise ValueError('Incomplete generation: finish_reason=' + str(choice.get('finish_reason')))
        message = choice.get('message')
        if not isinstance(message, dict):
            raise ValueError('Missing assistant message')
        if message.get('tool_calls') is not None and not isinstance(message['tool_calls'], list):
            raise ValueError('Invalid tool_calls list')
        return message

    def run(self):
        if self.args.stage in ('metadata', 'all'):
            reply = self.request('models', '/models')
            models = reply.get('data')
            if not isinstance(models, list) or not models or len(models) > 1000 or any(
                    not isinstance(m, dict) or not isinstance(m.get('id'), str) or not m['id'].strip()
                    or len(m['id']) > 200 or any(ord(c) < 32 for c in m['id']) for m in models):
                raise ValueError('Expected nonempty OpenAI data[] with exact model IDs')
            ids = [m['id'] for m in models]
            self.report['modelIds'] = ids
            self.check('models', modelIds=ids)
            if self.args.model and self.args.model not in ids:
                raise ValueError('Selected model ID is absent from /v1/models; no inference sent')
            status = self.request('status', '/status', optional=True)
            if status is not None:
                self.report['serverStatus'] = {k: status.get(k) for k in
                    ('service', 'model', 'loaded', 'auto_load', 'engine', 'context', 'concurrency', 'activity', 'last_timings')}
                self.log('server.status', **self.report['serverStatus'])
        if self.args.stage in ('chat', 'all'):
            reply = self.request('chat', '/chat/completions', self.payload([
                {'role': 'user', 'content': 'Reply with the word OK.'}]))
            message = self.message(reply)
            if message.get('tool_calls') or not isinstance(message.get('content'), str) or not message['content'].strip():
                raise ValueError('Expected a visible text answer without tools')
            self.report['capabilities']['chat'] = True
            self.check('chat', answerPreview=message['content'][:200], responseModel=reply.get('model'))
        if self.args.stage in ('tools', 'all'):
            nonce = 'strata-check-' + uuid.uuid4().hex[:12]
            receipt = 'receipt-' + uuid.uuid4().hex[:16]
            tools = [{'type': 'function', 'function': {'name': 'diagnostic_echo',
                'description': 'Echo the test value and return a fresh receipt; no files or external actions.',
                'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}},
                               'required': ['value'], 'additionalProperties': False}}}]
            messages = [{'role': 'system', 'content': 'Use diagnostic_echo exactly once as requested. '
                'After its result, answer with only the returned receipt and make no more tool calls.'},
                {'role': 'user', 'content': 'Call diagnostic_echo with value ' + nonce}]
            reply = self.request('tool-call', '/chat/completions', self.payload(messages, tools=tools, stream=True))
            message = self.message(reply)
            calls = message.get('tool_calls')
            if not isinstance(calls, list) or len(calls) != 1:
                raise ValueError('Model did not produce exactly one tool call')
            call = calls[0]
            if not isinstance(call, dict) or call.get('type') != 'function' or not isinstance(call.get('id'), str) or not call['id']:
                raise ValueError('Invalid tool call type/id')
            fn = call.get('function', {})
            if fn.get('name') != 'diagnostic_echo' or not isinstance(fn.get('arguments'), str) or json.loads(fn['arguments']) != {'value': nonce}:
                raise ValueError('Incorrect tool function/arguments; no tool result sent')
            self.report['capabilities']['toolCall'] = True
            self.check('tool-call', responseFormat=self.report['requests'][-1]['responseFormat'])
            messages.extend([{'role': 'assistant', 'content': message.get('content') or '', 'tool_calls': calls},
                {'role': 'tool', 'tool_call_id': call['id'], 'name': 'diagnostic_echo',
                 'content': json.dumps({'value': nonce, 'receipt': receipt})}])
            reply = self.request('tool-result', '/chat/completions', self.payload(messages, tools=tools, stream=True))
            message = self.message(reply)
            if message.get('tool_calls') or not isinstance(message.get('content'), str) or message['content'].strip() != receipt:
                raise ValueError('Model did not finish with the exact tool result')
            self.report['capabilities'].update(toolResult=True,
                sse=all(r.get('responseFormat') == 'text/event-stream' for r in self.report['requests'] if r['step'].startswith('tool-')))
            self.check('tool-result', **self.report['capabilities'])

    def finish(self, error=None, interrupted=False):
        self.report.update(finishedAt=datetime.now(timezone.utc).isoformat(),
            elapsedSeconds=round(time.monotonic()-self.started, 3),
            status='INTERRUPTED' if interrupted else 'FAIL' if error else {
                'metadata': 'METADATA_ONLY_PASS', 'chat': 'CHAT_PASS',
                'tools': 'TOOL_ROUNDTRIP_PASS', 'all': 'COMPATIBILITY_PASS'}[self.args.stage])
        if error:
            self.report['error'] = str(error)[:1000]
        self.log('diagnostic.finished', status=self.report['status'], elapsedSeconds=self.report['elapsedSeconds'])
        (self.directory/'report.json').write_text(json.dumps(self.clean(self.report), ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
        archive = self.directory.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name in ('report.json', 'events.jsonl'):
                bundle.write(self.directory/name, name)
        print('STRATA_TEST_STATUS ' + self.report['status'], flush=True)
        print('STRATA_TEST_SUPPORT ' + str(archive.resolve()), flush=True)
        return 130 if interrupted else 1 if error else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--base-url', help='Literal OpenAI base URL; default http://127.0.0.1:8081/v1')
    target.add_argument('--host', help='Explicit Windows IPv4, or auto for the WSL NAT gateway; no fallback')
    parser.add_argument('--port', type=int, help='With --host only; default 8081')
    parser.add_argument('--stage', choices=STAGES, default='metadata')
    parser.add_argument('--api-only', action='store_true', help='Alias for --stage metadata')
    parser.add_argument('--interactive', action='store_true', help='Choose metadata/chat/tools/all from a menu')
    parser.add_argument('--model', help='Exact ID from metadata; required for any generation stage')
    parser.add_argument('--connect-timeout', type=float, default=5, help='TCP/TLS connect limit, seconds')
    parser.add_argument('--metadata-timeout', type=float, default=15, help='Absolute limit per metadata request')
    parser.add_argument('--timeout', type=float, default=120, help='Absolute limit per generation request')
    parser.add_argument('--max-tokens', type=int, default=256)
    parser.add_argument('--reasoning-effort', choices=('default', 'none', 'low', 'medium', 'high'), default='default',
                        help='default omits the field, matching current production payloads')
    parser.add_argument('--api-key-env', default='STRATA_API_KEY', help='Read key from this environment variable; never saved')
    parser.add_argument('--out-dir', default='.local/strata-tests')
    args = parser.parse_args(argv)
    if args.interactive:
        if not sys.stdin.isatty():
            parser.error('--interactive requires a terminal; use --stage in scripts')
        print('1. Metadata only (no generation)\n2. One text generation\n3. Streaming tool round trip (2 calls)\n4. All (3 model calls)')
        choice = input('Choose 1-4 [1]: ').strip() or '1'
        if choice not in ('1', '2', '3', '4'):
            parser.error('Choose 1, 2, 3 or 4')
        args.stage = STAGES[int(choice)-1]
        if args.stage != 'metadata' and not args.model:
            args.model = input('Exact model ID: ').strip()
    if args.api_only and args.stage != 'metadata':
        parser.error('--api-only conflicts with a generation stage')
    if any(not math.isfinite(t) or not 0 < t <= 3600 for t in (args.connect_timeout, args.metadata_timeout, args.timeout)):
        parser.error('Timeouts must be finite numbers in (0, 3600]')
    if not 1 <= args.max_tokens <= 8192 or args.port is not None and not 1 <= args.port <= 65535:
        parser.error('Use 1..8192 max tokens and 1..65535 port')
    if args.model is not None and (not args.model.strip() or len(args.model) > 200 or any(ord(c) < 32 for c in args.model)):
        parser.error('Use an exact nonempty model ID, at most 200 characters')
    if args.stage != 'metadata' and not args.model:
        parser.error('Generation requires --model; run metadata first')
    if not args.api_key_env.isidentifier():
        parser.error('--api-key-env must be an environment variable name')
    try:
        base, selection = endpoint(args)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    try:
        diagnostic = Diagnostic(args, base, selection)
    except OSError as exc:
        print('Could not create diagnostic report directory: ' + str(exc), file=sys.stderr)
        return 3
    error, interrupted = None, False
    try:
        diagnostic.log('diagnostic.started', baseUrl=base, stage=args.stage, endpointSelection=selection,
                       model=args.model, reasoningEffort=args.reasoning_effort)
        diagnostic.run()
    except KeyboardInterrupt:
        error, interrupted = 'Stopped by operator; remote generation may continue', True
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    try:
        return diagnostic.finish(error, interrupted)
    except OSError as exc:
        print('Could not finish diagnostic reports: ' + str(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(worker() if sys.argv[1:] == ['--_worker'] else main())
