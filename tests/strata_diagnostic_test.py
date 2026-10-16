"""Focused standalone Strata diagnostics; loopback only, no model or SDK download."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/test_windows_strata.py'
spec = importlib.util.spec_from_file_location('strata_diagnostic', SCRIPT)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class Server(ThreadingHTTPServer):
    def handle_error(self, request, address):
        pass


class Handler(BaseHTTPRequestHandler):
    mode = 'ok'
    calls = []
    entered = threading.Event()
    release = threading.Event()
    samples = []

    def log_message(self, *args):
        pass

    def reply(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.calls.append((self.path, None, dict(self.headers)))
        self.entered.set()
        if self.mode == 'headers-stall':
            self.release.wait(5)
            return
        if self.mode == 'body-stall':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '1000')
            self.end_headers()
            self.wfile.write(b'{'); self.wfile.flush()
            self.release.wait(5)
            return
        if self.mode == 'trickle':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            while not self.release.wait(.025):
                self.wfile.write(b' '); self.wfile.flush()
            return
        if self.mode == 'redirect':
            self.send_response(302)
            self.send_header('Location', '/must-not-follow')
            self.end_headers()
            return
        if self.mode == 'auth-error':
            self.reply({'error': os.environ.get('STRATA_TEST_SECRET', 'sensitive-error-body')}, 401)
            return
        if self.path == '/v1/models':
            self.reply({'data': [] if self.mode == 'empty-models' else [{'id': 'fixture-model'}]})
        elif self.path == '/v1/status':
            self.reply({'service': 'strata', 'model': 'fixture-model', 'loaded': True},
                       404 if self.mode == 'no-status' else 200)
        else:
            self.reply({}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, body, dict(self.headers)))
        if self.mode == 'post-unsupported':
            self.reply({'error': 'unsupported tools'}, 400)
            return
        if 'tools' not in body:
            self.reply({'model': 'fixture-model', 'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}]})
            return
        messages = body['messages']
        if messages[-1]['role'] == 'tool':
            value = json.loads(messages[-1]['content'])['receipt']
            message = {'content': value if self.mode != 'bad-final' else 'different'}
            finish = 'stop'
        else:
            value = messages[-1]['content'].split()[-1]
            arguments = '{' if self.mode == 'bad-arguments' else json.dumps({'value': value})
            message = {'content': '', 'tool_calls': [{'id': 'test-call', 'type': 'function',
                       'function': {'name': 'diagnostic_echo', 'arguments': arguments}}]}
            finish = 'length' if self.mode == 'length' else 'tool_calls'
        if self.mode == 'json-fallback':
            self.reply({'model': 'fixture-model', 'choices': [{'message': message, 'finish_reason': finish}]})
            return
        deltas = [{'role': 'assistant', 'content': ''}]
        if message.get('tool_calls'):
            call = message['tool_calls'][0]
            deltas.append({'tool_calls': [{'index': 0, 'id': call['id'], 'type': 'function',
                                          'function': {'name': 'diagnostic_echo', 'arguments': ''}}]})
            arg = call['function']['arguments']
            deltas.extend({'tool_calls': [{'index': 0, 'function': {'arguments': s}}]} for s in [arg[:8], arg[8:]])
        else:
            deltas.append(message)
        chunks = [{'model': 'fixture-model', 'choices': [{'index': 0, 'delta': d, 'finish_reason': None}]} for d in deltas]
        chunks.append({'model': 'fixture-model', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})
        Handler.samples.append(chunks)
        raw = (': keep-alive\n\n' + ''.join('data: '+json.dumps(c)+'\n\n' for c in chunks) +
               ('' if self.mode == 'missing-done' else 'data: [DONE]\n\n')).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class StrataDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        Handler.mode, Handler.calls, Handler.samples = 'ok', [], []
        Handler.entered, Handler.release = threading.Event(), threading.Event()
        self.server = Server(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}/v1'

    def tearDown(self):
        Handler.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def command(self, *options):
        return [sys.executable, str(SCRIPT), '--base-url', self.base, '--out-dir', self.temp.name,
                '--metadata-timeout', '15', '--timeout', '30', *options]

    def run_check(self, *options, env=None, expected=0):
        result = subprocess.run(self.command(*options), capture_output=True, text=True, timeout=45, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        path = next(Path(self.temp.name).rglob('report.json'))
        report = json.loads(path.read_text())
        with zipfile.ZipFile(path.parent.with_suffix('.zip')) as z:
            self.assertEqual(set(z.namelist()), {'report.json', 'events.jsonl'})
            self.assertEqual(json.loads(z.read('report.json')), report)
        self.assertTrue(all(r.get('workerReaped') for r in report['requests']))
        return report, result

    def test_metadata_default_is_proxy_free_and_never_generates(self):
        env = {**os.environ, 'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1',
               'ALL_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': '', 'no_proxy': ''}
        report, _ = self.run_check(env=env)
        self.assertEqual(report['status'], 'METADATA_ONLY_PASS')
        self.assertEqual(report['modelRequests'], 0)
        self.assertEqual([c[0] for c in Handler.calls], ['/v1/models', '/v1/status'])
        self.assertTrue(all(c[1] is None for c in Handler.calls))

    def test_all_proves_text_sse_tool_result_and_production_accumulator(self):
        report, _ = self.run_check('--stage', 'all', '--model', 'fixture-model')
        self.assertEqual(report['status'], 'COMPATIBILITY_PASS')
        self.assertEqual(report['modelRequests'], 3)
        self.assertEqual(report['capabilities'], {'chat': True, 'toolCall': True, 'toolResult': True, 'sse': True})
        posts = [c[1] for c in Handler.calls if c[1] is not None]
        self.assertEqual([p['stream'] for p in posts], [False, True, True])
        self.assertTrue(all(p['temperature'] == 0 and p['max_tokens'] == 256 for p in posts))
        self.assertTrue(all('reasoning_effort' not in p for p in posts))
        sys.path.insert(0, str(ROOT/'scripts'))
        from repair_transport import ToolAccumulator
        for chunks in Handler.samples:
            accumulator = ToolAccumulator()
            for chunk in chunks:
                accumulator.add(chunk)
            self.assertTrue(accumulator.reply()['choices'])
        self.assertEqual(posts[-1]['messages'][-1]['role'], 'tool')
        self.assertEqual(posts[-1]['messages'][-1]['tool_call_id'], 'test-call')

    def test_stage_tools_skips_metadata_and_records_explicit_reasoning(self):
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model', '--reasoning-effort', 'none')
        self.assertEqual(len(Handler.calls), 2)
        self.assertTrue(all(c[1]['reasoning_effort'] == 'none' for c in Handler.calls))
        self.assertEqual(report['status'], 'TOOL_ROUNDTRIP_PASS')

    def test_json_fallback_is_supported_but_does_not_claim_sse(self):
        Handler.mode = 'json-fallback'
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model')
        self.assertTrue(report['capabilities']['toolResult'])
        self.assertFalse(report['capabilities']['sse'])

    def test_invalid_tool_arguments_stop_before_tool_result(self):
        Handler.mode = 'bad-arguments'
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model', expected=1)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(len(Handler.calls), 1)
        self.assertFalse(report['capabilities'].get('toolResult', False))

    def test_truncated_tool_call_is_never_a_pass(self):
        Handler.mode = 'length'
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model', expected=1)
        self.assertIn('finish_reason=length', report['error'])
        self.assertEqual(len(Handler.calls), 1)

    def test_missing_sse_done_fails_without_resend(self):
        Handler.mode = 'missing-done'
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model', expected=1)
        self.assertIn('before [DONE]', report['error'])
        self.assertEqual(len(Handler.calls), 1)

    def test_tool_result_requires_matching_final_answer(self):
        Handler.mode = 'bad-final'
        report, _ = self.run_check('--stage', 'tools', '--model', 'fixture-model', expected=1)
        self.assertEqual(len(Handler.calls), 2)
        self.assertFalse(report['capabilities'].get('toolResult', False))

    def test_empty_models_prevent_inference(self):
        Handler.mode = 'empty-models'
        report, _ = self.run_check('--stage', 'all', '--model', 'fixture-model', expected=1)
        self.assertEqual(report['modelRequests'], 0)
        self.assertEqual(len(Handler.calls), 1)

    def test_missing_optional_status_is_not_a_metadata_failure(self):
        Handler.mode = 'no-status'
        report, _ = self.run_check('--api-only')
        self.assertEqual(report['status'], 'METADATA_ONLY_PASS')
        self.assertEqual(report['requests'][-1]['status'], 'unsupported')

    def test_http_error_does_not_copy_remote_body_or_credentials(self):
        Handler.mode = 'auth-error'
        secret = 'fixture-only-strata-key'
        env = {**os.environ, 'STRATA_API_KEY': secret}
        report, result = self.run_check(env=env, expected=1)
        self.assertEqual(report['requests'][0]['httpStatus'], 401)
        self.assertEqual(len(Handler.calls), 1)
        self.assertEqual(Handler.calls[0][2]['Authorization'], 'Bearer '+secret)
        for p in Path(self.temp.name).rglob('*'):
            if p.is_file():
                self.assertNotIn(secret.encode(), p.read_bytes())
                self.assertNotIn(b'sensitive-error-body', p.read_bytes())
        self.assertNotIn(secret, result.stdout+result.stderr)

    def test_redirect_is_not_followed(self):
        Handler.mode = 'redirect'
        report, _ = self.run_check(expected=1)
        self.assertEqual(report['requests'][0]['httpStatus'], 302)
        self.assertEqual(len(Handler.calls), 1)

    def test_connection_refusal_preserves_connect_failure_without_fallback(self):
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            base = f'http://127.0.0.1:{reserved.getsockname()[1]}/v1'
            report, _ = self.run_check('--base-url', base, expected=1)
        request = report['requests'][0]
        self.assertEqual(request['phase'], 'connect.started')
        self.assertIsNotNone(request['failure']['errno'])
        self.assertEqual(request['url'], base+'/models')
        self.assertEqual(Handler.calls, [])

    def test_expired_cold_child_is_reaped_before_network_dispatch(self):
        args = SimpleNamespace(api_key_env='STRATA_API_KEY', out_dir=self.temp.name,
            stage='metadata', model=None, reasoning_effort='default', max_tokens=256,
            connect_timeout=5, metadata_timeout=.3, timeout=30)
        client = diagnostic.Diagnostic(args, self.base, 'explicit-base-url')
        popen = subprocess.Popen

        def cold_child(argv, **kwargs):
            return popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        with patch.object(diagnostic.subprocess, 'Popen', side_effect=cold_child):
            with self.assertRaises(TimeoutError):
                client.request('models', '/models')
        client.finish('Controlled cold-start timeout')
        self.assertEqual(client.report['requests'][0]['phase'], 'worker.starting')
        self.assertTrue(client.report['requests'][0]['workerReaped'])
        self.assertEqual(Handler.calls, [])

    def test_redaction_preserves_schema_even_for_short_keys(self):
        args = SimpleNamespace(api_key_env='STRATA_API_KEY', out_dir=self.temp.name,
            stage='metadata', model=None, reasoning_effort='default', max_tokens=256,
            connect_timeout=5, metadata_timeout=15, timeout=30)
        with patch.dict(os.environ, {'STRATA_API_KEY': 'a'}):
            client = diagnostic.Diagnostic(args, self.base, 'explicit-base-url')
        self.assertEqual(client.clean({'status': 'a', 'data': ['a']}),
                         {'status': '[REDACTED]', 'data': ['[REDACTED]']})

    def check_deadline(self, mode, phase):
        Handler.mode = mode
        args = SimpleNamespace(api_key_env='STRATA_API_KEY', out_dir=self.temp.name,
            stage='metadata', model=None, reasoning_effort='default', max_tokens=256,
            connect_timeout=10, metadata_timeout=30, timeout=30)
        client = diagnostic.Diagnostic(args, self.base, 'explicit-base-url')
        advance, errors = [0], []
        clock = SimpleNamespace(monotonic=lambda: time.monotonic()+advance[0])

        def run():
            try:
                client.request('models', '/models')
            except Exception as exc:
                errors.append(exc)
        # Start a real child and observe the intended I/O phase before expiring
        # only the controller's clock. Cold imports cannot masquerade as body I/O.
        with patch.object(diagnostic, 'time', clock):
            thread = threading.Thread(target=run)
            thread.start()
            try:
                deadline = time.monotonic()+15
                while time.monotonic() < deadline:
                    if client.report['requests'] and client.report['requests'][0]['phase'] == phase:
                        break
                    if errors:
                        self.fail(str(errors))
                    time.sleep(.01)
                self.assertEqual(client.report['requests'][0]['phase'], phase)
                advance[0] = 31
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertIsInstance(errors[0], TimeoutError)
                client.finish(str(errors[0]))
            finally:
                Handler.release.set()
                thread.join(5)
        self.assertEqual(len(Handler.calls), 1)
        self.assertTrue(client.report['requests'][0]['workerReaped'])

    def test_absolute_deadline_stops_silent_headers_and_reaps_worker(self):
        self.check_deadline('headers-stall', 'response.waiting')

    def test_absolute_deadline_stops_silent_body(self):
        self.check_deadline('body-stall', 'response.reading')

    def test_absolute_deadline_stops_trickle_body(self):
        self.check_deadline('trickle', 'response.reading')

    @unittest.skipUnless(os.name == 'posix', 'Signal test exercises the WSL/Linux controller')
    def test_interrupt_keeps_report_and_reaps_owned_worker(self):
        Handler.mode = 'headers-stall'
        process = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(Handler.entered.wait(15))
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130, stdout+stderr)
            report = json.loads(next(Path(self.temp.name).rglob('report.json')).read_text())
            self.assertEqual(report['status'], 'INTERRUPTED')
            self.assertTrue(report['requests'][0]['workerReaped'])
            self.assertTrue(list(Path(self.temp.name).glob('*.zip')))
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close(); process.stderr.close()

    def test_endpoint_is_literal_and_gateway_requires_explicit_selection(self):
        args = argparse_args()
        with patch.object(diagnostic.subprocess, 'check_output') as command:
            self.assertEqual(diagnostic.endpoint(args), ('http://127.0.0.1:8081/v1', 'provided-loopback-default'))
            command.assert_not_called()
        args.host = 'auto'
        with patch.object(diagnostic.platform, 'release', return_value='microsoft-standard-WSL2'), \
                patch.object(diagnostic.subprocess, 'check_output', return_value='[{"gateway":"192.0.2.1"}]'):
            self.assertEqual(diagnostic.endpoint(args), ('http://192.0.2.1:8081/v1', 'explicit-gateway'))

    def test_invalid_cli_fails_before_any_network_request(self):
        for options in [('--stage', 'all'), ('--base-url', 'http://u:p@127.0.0.1/v1'),
                        ('--base-url', 'http://127.0.0.1/v1?'), ('--timeout', 'nan'), ('--port', '0')]:
            result = subprocess.run(self.command(*options), capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertEqual(Handler.calls, [])


def argparse_args():
    from argparse import Namespace
    return Namespace(base_url=None, host=None, port=None)


if __name__ == '__main__':
    unittest.main()
