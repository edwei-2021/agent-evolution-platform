"""Real subprocess/model-HTTP workflow tests with a loopback mock, never Windows."""
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_service import RuntimeService, ROLES
from ollama_bridge import DEFAULTS
from llm_engine import ENGINE, messages, output, skill, splits, verify
from serve_gui import GuiHandler, DIST


def registry():
    return {'agents': [{'id': f'AG-{i}', 'name': role, 'role': role, 'enabled': True} for i, role in enumerate(ROLES)]}


def finish(service, identifier):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = service.get_run(identifier)
        if run['status'] in ('completed', 'cancelled', 'failed', 'interrupted'):
            return run
        time.sleep(.025)
    raise AssertionError('LLM workflow did not finish')


class MockModel(BaseHTTPRequestHandler):
    calls = []
    mode = 'improve'
    block = None
    entered = threading.Event()

    def log_message(self, *args): pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(request); self.entered.set()
        if self.block: self.block.wait(5)
        system = request['messages'][0]['content']
        if self.mode == 'http-error':
            data, status = {'error': 'mock unavailable'}, 503
        else:
            if 'Improve the Skill' in system:
                body = 'Return the input unchanged.' if self.mode == 'no-gain' else 'CLEAN: Apply NFKC and case folding, trim and collapse whitespace.'
                value = {'body': body, 'name': 'bad'} if self.mode == 'bad-reflection' else {'body': body}
            else:
                text = json.loads(request['messages'][1]['content'])['input']
                if 'CLEAN:' in system:
                    text = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold().strip())
                value = {'output': text}
            data = {'model': request['model'], 'choices': [{'message': {'content': json.dumps(value)}}],
                    'usage': {'prompt_tokens': 20, 'completion_tokens': 10}}
            status = 200
        raw = json.dumps(data).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass


class LlmWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.service = RuntimeService(self.temp.name)
        MockModel.calls = []; MockModel.mode = 'improve'; MockModel.block = None; MockModel.entered.clear()
        self.model = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        self.thread = threading.Thread(target=self.model.serve_forever, daemon=True); self.thread.start()
        self.service.ollama.save({**DEFAULTS, 'host': '127.0.0.1', 'port': self.model.server_port,
                                 'model': 'mock-local:1', 'inferenceTimeout': 10}, 0)

    def tearDown(self):
        if MockModel.block: MockModel.block.set()
        self.service.close(); self.model.shutdown(); self.model.server_close(); self.thread.join(); self.temp.cleanup()

    def options(self, revision=1):
        return {'profile': 'smoke', 'maxSeconds': 60, 'expectedRevision': revision, 'providerRevision': 1}

    def start(self, name='model', revision=1):
        return self.service.start(registry(), name, 'llm-evolution', self.options(revision))

    def test_actual_worker_reflection_evaluation_review_and_versions(self):
        self.service.stage_timeout = .001  # LLM uses its whole-run deadline, not the tool-stage timeout.
        self.assertEqual(MockModel.calls, [])
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'completed', done)
        self.assertEqual([a['role'] for a in done['agents']], ['coordinator', 'worker', 'reflector', 'evaluator', 'reviewer'])
        self.assertTrue(all(a['pid'] and a['exitCode'] == 0 for a in done['agents']))
        self.assertEqual(done['llmResult']['calls'], 15)
        self.assertEqual(len(MockModel.calls), 15)
        self.assertEqual(done['llmResult']['baselineValidation']['passed'], 0)
        self.assertEqual(done['llmResult']['selectedValidation']['passed'], 2)
        self.assertTrue(done['llmResult']['eligible'])
        self.assertEqual(self.service.llm.snapshot()['activeVersionId'], 'LSV-baseline')
        self.assertFalse(self.service.ollama.operation.locked())
        reflection = MockModel.calls[5]
        feedback = json.loads(reflection['messages'][1]['content'])['trainingFailures']
        self.assertTrue(all(r['taskId'].startswith('TR-') for r in feedback))
        self.assertTrue(all('expected' not in json.loads(c['messages'][1]['content']) for c in MockModel.calls if c is not reflection))
        count = len(MockModel.calls)
        path = self.service.local / 'runs' / done['id']
        self.assertEqual(verify(path), done['llmResult'])
        state = self.service.llm.approve(done['id'], 1)
        self.assertEqual(state['active']['label'], 'L1'); self.assertEqual(state['revision'], 2)
        self.assertEqual(len(MockModel.calls), count)  # Approval/reviewer do not re-infer.
        state = self.service.llm.activate('LSV-baseline', 2)
        self.assertEqual(state['revision'], 3)
        self.assertEqual(self.service.skills.snapshot()['activeVersionId'], 'SKV-baseline')
        self.service.close(); self.service = RuntimeService(self.temp.name)
        self.assertEqual(len(self.service.llm.snapshot()['versions']), 2)
        self.assertEqual(self.service.llm.snapshot()['activeVersionId'], 'LSV-baseline')

    def test_no_gain_preserves_baseline_and_counts_fewer_holdout_calls(self):
        MockModel.mode = 'no-gain'
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(done['llmResult']['selectedId'], 'C0')
        self.assertFalse(done['llmResult']['eligible']); self.assertEqual(len(MockModel.calls), 13)
        with self.assertRaises(RuntimeError): self.service.llm.approve(done['id'], 1)

    def test_provider_errors_are_not_retried_or_scored_as_success(self):
        MockModel.mode = 'http-error'
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'failed'); self.assertEqual(len(MockModel.calls), 1)
        self.assertNotIn('llmResult', done)
        calls = json.loads((self.service.local / 'runs' / done['id'] / 'llm-calls.json').read_text())
        self.assertEqual(calls[0]['status'], 'failed')
        self.assertFalse(self.service.ollama.operation.locked())

    def test_reflector_cannot_change_metadata_and_failure_skips_evaluator(self):
        MockModel.mode = 'bad-reflection'
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'failed'); self.assertEqual(len(MockModel.calls), 6)
        self.assertEqual(next(a for a in done['agents'] if a['role'] == 'evaluator')['status'], 'skipped')

    def test_evidence_tampering_blocks_human_release(self):
        done = finish(self.service, self.start()['id'])
        path = self.service.local / 'runs' / done['id'] / 'llm-calls.json'
        calls = json.loads(path.read_text())
        calls[6]['response']['choices'][0]['message']['content'] = json.dumps({'output': 'tampered'})
        path.write_text(json.dumps(calls))
        with self.assertRaises(ValueError): self.service.llm.approve(done['id'], 1)
        self.assertEqual(self.service.llm.snapshot()['revision'], 1)

    def test_cancel_stops_future_calls_and_shared_slot_rejects_other_work(self):
        MockModel.block = threading.Event()
        run = self.start()
        self.assertTrue(MockModel.entered.wait(5))
        with self.assertRaises(RuntimeError): self.service.start(registry(), 'another')
        with self.assertRaises(RuntimeError): self.service.ollama.run('metadata', 1)
        self.service.cancel(run['id'])
        done = finish(self.service, run['id'])
        self.assertEqual(done['status'], 'cancelled'); self.assertEqual(len(MockModel.calls), 1)
        self.assertFalse(self.service.ollama.operation.locked())
        with self.assertRaises(RuntimeError): self.service.llm.approve(run['id'], 1)

    def test_invalid_or_stale_configuration_and_idempotent_replay(self):
        for options in [{**self.options(), 'maxSeconds': True}, {**self.options(), 'profile': 'other'}, {**self.options(), 'providerRevision': 2}]:
            with self.assertRaises((ValueError, RuntimeError)):
                self.service.start(registry(), 'invalid', 'llm-evolution', options)
        self.assertEqual(MockModel.calls, [])
        run = self.start()
        done = finish(self.service, run['id'])
        count = len(MockModel.calls)
        self.assertEqual(self.start()['id'], done['id']); self.assertEqual(len(MockModel.calls), count)
        with self.assertRaises(RuntimeError): self.service.start(registry(), 'model', 'llm-evolution', {**self.options(), 'profile': 'full'})

    def test_full_profile_has_exact_call_accounting_and_separate_holdout_selection(self):
        run = self.service.start(registry(), 'full', 'llm-evolution', {**self.options(), 'profile': 'full'})
        done = finish(self.service, run['id'])
        self.assertEqual(done['status'], 'completed', done)
        self.assertEqual(done['llmResult']['calls'], 101)
        self.assertEqual(done['llmResult']['selectedValidation']['total'], 10)
        self.assertEqual(done['llmResult']['heldout']['selected']['total'], 20)
        self.assertEqual(len(MockModel.calls), 101)

    def test_whole_run_deadline_terminates_waiting_process_and_prevents_more_calls(self):
        MockModel.block = threading.Event()
        run = self.start()
        self.assertTrue(MockModel.entered.wait(5))
        # Fault injection shortens the already frozen deadline; public API minimum remains 60 s.
        with self.service.lock:
            self.service.current['llmConfig']['maxSeconds'] = .001
        done = finish(self.service, run['id'])
        self.assertEqual(done['status'], 'failed')
        self.assertEqual(len(MockModel.calls), 1)
        self.assertFalse(self.service.ollama.operation.locked())
        self.assertEqual(next(a for a in done['agents'] if a['role'] == 'worker')['error'], 'Stage timed out')

    def test_local_http_submission_history_approval_and_rollback(self):
        class Quiet(GuiHandler):
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
        server.runtime = self.service
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, body=None, token=True):
            headers = {'Content-Type': 'application/json', 'Origin': base}
            if token: headers['X-Lab-Token'] = self.service.csrf_token
            with urlopen(Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers), timeout=5) as response:
                return json.load(response)
        try:
            self.assertEqual(request('/api/v1/llm/skills')['activeVersionId'], 'LSV-baseline')
            self.assertEqual(MockModel.calls, [])
            body = {'registry': registry(), 'requestId': 'api', **self.options()}
            with self.assertRaises(HTTPError) as exc: request('/api/v1/llm/skills/runs', body, False)
            self.assertEqual(exc.exception.code, 403)
            run = request('/api/v1/llm/skills/runs', body)
            finish(self.service, run['id'])
            self.assertEqual(request('/api/v1/runtime')['llm']['latestRun']['id'], run['id'])
            state = request(f'/api/v1/llm/skills/runs/{run["id"]}/approve', {'expectedRevision': 1})
            self.assertEqual(state['active']['label'], 'L1')
            state = request('/api/v1/llm/skills/versions/LSV-baseline/activate', {'expectedRevision': 2})
            self.assertEqual(state['activeVersionId'], 'LSV-baseline')
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_browser_client_polls_real_api_through_completion_and_version_review(self):
        from setup_wsl import find_node
        node = find_node()
        if not node:
            self.skipTest('Supported Linux Node required for transport integration')
        class Quiet(GuiHandler):
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
        server.runtime = self.service
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        root = Path(__file__).resolve().parents[1]
        client_uri = (root / 'dist/js/runtime-client.js').as_uri()
        agents_uri = (root / 'dist/js/agents.js').as_uri()
        js = f"""
import assert from 'node:assert/strict';
import {{RuntimeClient}} from {json.dumps(client_uri)};
import {{initialRegistry}} from {json.dumps(agents_uri)};
const base='http://127.0.0.1:{server.server_port}';
const client=new RuntimeClient({{fetcher:(path,options)=>fetch(base+path,options)}});
assert.equal(await client.refresh(),true);
client.llmSeconds=60;await client.startLlm(initialRegistry());
for(let i=0;i<160;i++){{
  assert.equal(await client.refresh(),true,client.error);
  if(client.data.llm.latestRun.status==='completed')break;
  await new Promise(resolve=>setTimeout(resolve,50));
}}
assert.equal(client.data.llm.latestRun.status,'completed');
assert.equal(client.data.llm.latestRun.llmResult.calls,15);
await client.selectLlmRun(client.data.llm.latestRun.id);
await client.approveLlm(client.data.llm.latestRun.id);
assert.equal(client.data.llm.active.label,'L1');
await client.activateLlm('LSV-baseline');
assert.equal(client.data.llm.activeVersionId,'LSV-baseline');
assert.equal(client.data.skills.activeVersionId,'SKV-baseline');
console.log(JSON.stringify({{polls:client.pollCount,status:'PASS'}}));
"""
        try:
            result = subprocess.run([node['path'], '--input-type=module', '-e', js], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'PASS')
            self.assertEqual(len(MockModel.calls), 15)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class ProtocolTests(unittest.TestCase):
    def test_protocol_preserves_whitespace_and_rejects_unstructured_answers(self):
        for body in ('', ' ' * 3001, 'valid' + ' ' * 3000, '\x00'):
            with self.assertRaises(ValueError): skill(body)
        reply = lambda value: {'choices': [{'message': {'content': value}}]}
        self.assertEqual(output(reply('{"output":"  hi\\n"}')), ('  hi\n', None))
        self.assertIsNone(output(reply('hi'))[0])
        self.assertIsNone(output(reply('{"output":1}'))[0])
        self.assertEqual(set(json.loads(messages(skill('Return input.'), 'input')[1]['content'])), {'input'})
        data = splits('smoke')
        self.assertEqual([len(data[k]) for k in ('train', 'validation', 'heldout')], [3, 2, 2])
        self.assertEqual(len({r['group'] for rows in data.values() for r in rows}), 7)


if __name__ == '__main__': unittest.main()
