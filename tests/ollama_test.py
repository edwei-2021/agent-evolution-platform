"""Offline provider integration. Mock HTTP only; never contacts Windows Ollama."""
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ollama_bridge as bridge
from runtime_service import RuntimeService
from serve_gui import GuiHandler, DIST


class MockOllama(BaseHTTPRequestHandler):
    calls = []
    mode = 'ok'

    def log_message(self, *args): pass

    def do_GET(self):
        self.calls.append((self.path, None))
        data = {'/api/version': {'version': 'mock-0.40.2'},
                '/api/tags': {'models': [{'name': 'test-model:local'}]},
                '/v1/models': {'data': [{'id': 'test-model:local'}]}}.get(self.path, {})
        if self.mode == 'bad-models' and self.path == '/v1/models':
            data = {'data': ['invalid']}
        self.reply(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, body))
        if self.mode == 'http-error':
            self.reply({'error': 'model not found'}, 404)
        else:
            content = '' if self.mode == 'empty' else 'OK'
            self.reply({'choices': [{'message': {'content': content}}],
                        'model': body['model'], 'usage': {'completion_tokens': 1}})

    def reply(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Length', str(len(raw)))
        self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(raw)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        MockOllama.calls = []; MockOllama.mode = 'ok'
        self.mock = ThreadingHTTPServer(('127.0.0.1', 0), MockOllama)
        self.thread = threading.Thread(target=self.mock.serve_forever, daemon=True); self.thread.start()
        self.bridge = bridge.OllamaBridge(self.temp.name)
        self.config = {**bridge.DEFAULTS, 'host': '127.0.0.1',
                       'port': self.mock.server_port, 'model': 'test-model:local'}
        self.bridge.save(self.config, 0)

    def tearDown(self):
        self.mock.shutdown(); self.mock.server_close(); self.thread.join(); self.temp.cleanup()

    def test_save_snapshot_restart_and_export_make_no_http_calls(self):
        snapshot = self.bridge.snapshot()
        self.assertEqual(snapshot['revision'], 1)
        self.assertEqual(snapshot['historicalEvidence']['status'], 'METADATA_ONLY_PASS')
        self.assertFalse(snapshot['historicalEvidence']['inferenceTested'])
        self.assertEqual(len(snapshot['historicalEvidence']['modelIds']), 15)
        self.assertFalse(snapshot['workerIntegrated'])
        restarted = bridge.OllamaBridge(self.temp.name)
        self.assertEqual(restarted.state(), self.bridge.state())
        self.config['model'] = "test-model:local' ; $(printf must-not-run)"
        self.bridge.save(self.config, 1)
        target = Path(self.temp.name) / 'a folder/client.env'
        with patch.dict(os.environ, {'NO_PROXY': 'existing.internal'}):
            self.bridge.export_environment(target)
        script = 'source ' + shlex.quote(str(target)) + '; printf "%s\\n" "$OLLAMA_MODEL" "$OPENAI_BASE_URL" "$NO_PROXY"'
        output = subprocess.check_output(['bash', '-c', script], text=True)
        self.assertIn(self.config['model'], output)
        self.assertIn('existing.internal,localhost,127.0.0.1', output)
        self.assertEqual(MockOllama.calls, [])

    def test_default_port_and_gateway_are_dynamic_without_http_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            client = bridge.OllamaBridge(temp)
            with patch.object(bridge, 'gateway', side_effect=['172.22.160.1', '172.23.0.1']):
                self.assertEqual(client.snapshot()['openaiBaseUrl'], 'http://172.22.160.1:11435/v1')
                self.assertEqual(client.snapshot()['openaiBaseUrl'], 'http://172.23.0.1:11435/v1')
            with patch.object(bridge, 'gateway', side_effect=ValueError('Not WSL')):
                self.assertEqual(client.snapshot()['discoveryError'], 'Not WSL')
        self.assertEqual(MockOllama.calls, [])

    def test_route_discovery_rejects_ambiguous_routes_and_non_wsl(self):
        with patch.object(bridge.platform, 'release', return_value='microsoft-standard-WSL2'), patch.object(bridge.subprocess, 'check_output', return_value='[{"gateway":"172.22.160.1"}]'):
            self.assertEqual(bridge.gateway(), '172.22.160.1')
        with patch.object(bridge.platform, 'release', return_value='microsoft-standard-WSL2'), patch.object(bridge.subprocess, 'check_output', return_value='[{"gateway":"172.22.160.1"},{"gateway":"172.23.0.1"}]'):
            with self.assertRaises(ValueError): bridge.gateway()
        with patch.object(bridge.platform, 'release', return_value='linux'), patch.object(bridge.subprocess, 'check_output') as command:
            with self.assertRaises(ValueError): bridge.gateway()
            command.assert_not_called()

    def test_metadata_and_chat_bypass_broken_proxy_and_have_separate_evidence(self):
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1', 'NO_PROXY': '', 'no_proxy': ''}):
            metadata = self.bridge.run('metadata', 1)
            self.assertEqual(metadata['status'], 'METADATA_ONLY_PASS')
            self.assertFalse(metadata['inferenceTested'])
            self.assertEqual(metadata['modelIds'], ['test-model:local'])
            self.assertEqual(len(MockOllama.calls), 3)
            chat = self.bridge.run('chat', 1, 'Reply OK')
        self.assertEqual(chat['status'], 'INFERENCE_PASS'); self.assertEqual(chat['content'], 'OK')
        path, payload = MockOllama.calls[-1]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertFalse(payload['stream']); self.assertEqual(payload['max_tokens'], 256)
        self.assertEqual(payload['model'], 'test-model:local')
        records = list((Path(self.temp.name) / '.local/ollama').glob('request-*.json'))
        self.assertEqual(len(records), 2)
        self.assertEqual(self.bridge.snapshot()['latest']['status'], 'INFERENCE_PASS')
        self.bridge.save({**self.config, 'model': 'changed-model'}, 1)
        self.assertNotEqual(self.bridge.snapshot()['latest']['revision'], self.bridge.state()['revision'])

    def test_failures_are_recorded_and_no_retry_or_false_success_occurs(self):
        for mode in ('empty', 'http-error', 'bad-models'):
            MockOllama.mode = mode
            previous = len(MockOllama.calls)
            result = self.bridge.run('metadata' if mode == 'bad-models' else 'chat', 1, 'OK')
            self.assertEqual(result['status'], 'FAIL'); self.assertIn('error', result)
            self.assertEqual(len(MockOllama.calls) - previous, 3 if mode == 'bad-models' else 1)
        self.assertFalse(self.bridge.snapshot()['busy'])

    def test_invalid_config_revision_and_duplicate_operations_do_not_dispatch(self):
        for key, value in [('port', 0), ('port', True), ('host', 'http://localhost'), ('host', '0.0.0.0'), ('inferenceTimeout', float('nan')), ('model', 'bad\nmodel')]:
            with self.assertRaises(ValueError): self.bridge.save({**self.config, key: value}, 1)
        with self.assertRaises(RuntimeError): self.bridge.save(self.config, 99)
        with self.assertRaises(RuntimeError): self.bridge.run('chat', 99, 'OK')
        self.bridge.operation.acquire()
        try:
            with self.assertRaises(RuntimeError): self.bridge.run('chat', 1, 'OK')
        finally: self.bridge.operation.release()
        with self.assertRaises(ValueError): self.bridge.run('chat', 1, '')
        self.assertEqual(MockOllama.calls, [])

    def test_uploaded_diagnostic_is_preserved_and_api_only_never_sends_chat(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root / 'docs/verification/ollama-user-evidence.json').read_text())
        import hashlib
        script = root / 'scripts/test_windows_ollama.py'
        self.assertEqual(hashlib.sha256(script.read_bytes()).hexdigest(), evidence['diagnosticScriptSha256'])
        result = subprocess.run([sys.executable, str(script), '--host', '127.0.0.1', '--port', str(self.mock.server_port), '--api-only', '--out-dir', str(Path(self.temp.name) / 'logs')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(next((Path(self.temp.name) / 'logs').glob('*.json')).read_text())
        self.assertEqual(report['status'], 'METADATA_ONLY_PASS')
        self.assertTrue(all(body is None for _, body in MockOllama.calls))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.service = RuntimeService(self.temp.name)
        class Quiet(GuiHandler):
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
        self.server.runtime = self.service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.service.close(); self.temp.cleanup()

    def request(self, path, body=None, token=True, origin=None):
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.base}
        if token: headers['X-Lab-Token'] = self.service.csrf_token
        with urlopen(Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers), timeout=5) as response:
            return json.load(response)

    def test_settings_round_trip_csrf_origin_and_revision_guards(self):
        with patch.object(bridge.OllamaBridge, 'request') as request:
            state = self.request('/api/v1/llm/ollama')
            self.assertEqual(state['config']['port'], 11435)
            config = {**state['config'], 'host': '172.22.160.1', 'model': 'qwen3-coder:30b'}
            body = {'config': config, 'expectedRevision': 0}
            for token, origin in [(False, None), (True, 'http://evil.example')]:
                with self.assertRaises(HTTPError) as exc:
                    self.request('/api/v1/llm/ollama/settings', body, token, origin)
                self.assertEqual(exc.exception.code, 403)
            result = self.request('/api/v1/llm/ollama/settings', body)
            self.assertEqual(result['revision'], 1)
            self.assertEqual(result['openaiBaseUrl'], 'http://172.22.160.1:11435/v1')
            with self.assertRaises(HTTPError) as exc: self.request('/api/v1/llm/ollama/settings', body)
            self.assertEqual(exc.exception.code, 409)
            request.assert_not_called()


if __name__ == '__main__': unittest.main()
