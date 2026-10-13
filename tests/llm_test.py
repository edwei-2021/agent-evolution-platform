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
    run = service.get_run(identifier)
    # Functional completion follows the frozen workflow budget, not an
    # unrelated 20-second workstation-speed assumption. Model and workflow
    # limits still run in the supervisor; the 10 seconds is cleanup grace.
    budget = run['llmConfig']['maxSeconds'] + 10
    try:
        return service.wait_for_terminal(identifier,budget)
    except (TimeoutError,RuntimeError) as exc:
        raise AssertionError('LLM workflow has no terminal evidence within its workflow/cleanup budget') from exc


class MockModel(BaseHTTPRequestHandler):
    calls = []
    warmups = []
    mode = 'improve'
    block = None
    stream_block = None
    entered = threading.Event()

    def log_message(self, *args): pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/generate':
            self.warmups.append(request)
            raw=json.dumps({'model':request['model'],'done':True,'load_duration':400000000}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
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
        if self.mode in ('stream', 'stream-disconnect', 'stream-trickle'):
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            text = data['choices'][0]['message']['content']
            events = [{'model': request['model'], 'choices': [{'index': 0, 'delta': {'reasoning_content': '正在處理'}}]},
                      {'model': request['model'], 'choices': [{'index': 0, 'delta': {'content': text[:4]}}]},
                      {'model': request['model'], 'choices': [{'index': 0, 'delta': {'content': text[4:]}, 'finish_reason': 'stop'}]},
                      {'model': request['model'], 'choices': [], 'usage': data['usage']}]
            try:
                if self.mode == 'stream-trickle':
                    for _ in range(30):
                        self.wfile.write(b'data: {"choices":[{"delta":{"reasoning_content":"x"}}]}\n\n'); self.wfile.flush(); time.sleep(.1)
                for index, event in enumerate(events):
                    self.wfile.write(('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode()); self.wfile.flush()
                    if index == 0 and self.stream_block: self.stream_block.wait(5)
                if self.mode == 'stream': self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass
            return
        raw = json.dumps(data).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass


class LlmWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.service = RuntimeService(self.temp.name)
        MockModel.calls = []; MockModel.warmups = []; MockModel.mode = 'improve'; MockModel.block = None; MockModel.stream_block = None; MockModel.entered.clear()
        self.model = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        self.thread = threading.Thread(target=self.model.serve_forever, daemon=True); self.thread.start()
        self.service.ollama.save({**DEFAULTS, 'host': '127.0.0.1', 'port': self.model.server_port,
                                 'model': 'mock-local:1', 'inferenceTimeout': 10}, 0)

    def tearDown(self):
        if MockModel.block: MockModel.block.set()
        if MockModel.stream_block: MockModel.stream_block.set()
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
        self.assertEqual(done['llmProgress']['completedCalls'], 0)
        self.assertEqual(done['llmProgress']['lastCall']['status'], 'cancelled')
        self.assertIn('no further requests', done['llmProgress']['lastCall']['error'])
        self.assertFalse(self.service.ollama.operation.locked())
        with self.assertRaises(RuntimeError): self.service.llm.approve(run['id'], 1)

    def test_invalid_or_stale_configuration_and_idempotent_replay(self):
        for options in [{**self.options(), 'maxSeconds': True}, {**self.options(), 'profile': 'other'}, {**self.options(), 'providerRevision': 2},
                        *[{**self.options(), 'callTimeoutSeconds': value} for value in (True, 9, 3601, '120')]]:
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
        self.assertEqual(next(a for a in done['agents'] if a['role'] == 'worker')['error'], 'Workflow time limit exceeded')
        self.assertEqual(done['llmProgress']['lastCall']['status'], 'failed')

    def test_streamed_workflow_reassembles_evidence_and_reviewer_rejects_tampering(self):
        MockModel.mode = 'stream'
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'completed', done)
        self.assertEqual(done['llmProgress']['completedCalls'], 15)
        self.assertEqual(done['executionProgress']['completedStages'], 5)
        self.assertTrue(all(c['stream'] for c in MockModel.calls))
        path = self.service.local / 'runs' / done['id']
        self.assertEqual(verify(path), done['llmResult'])
        calls = json.loads((path / 'llm-calls.json').read_text())
        self.assertEqual(calls[0]['chunks'], 4)
        self.assertEqual(calls[0]['reasoningChars'], 4)
        self.assertGreater(calls[0]['outputChars'], 0)
        calls[0]['streamEvents'][1]['choices'][0]['delta']['content'] = 'tampered'
        (path / 'llm-calls.json').write_text(json.dumps(calls))
        with self.assertRaises(ValueError): self.service.llm.approve(done['id'], 1)

    def test_stream_progress_is_visible_before_completion_and_watchdog_stops_active_stream(self):
        MockModel.mode = 'stream'; MockModel.stream_block = threading.Event()
        run = self.start()
        until = time.monotonic() + 5
        while time.monotonic() < until:
            waiting = self.service.get_run(run['id'])
            call = waiting.get('llmProgress', {}).get('lastCall')
            if call and call.get('chunks'): break
            time.sleep(.025)
        self.assertEqual(call['status'], 'running')
        self.assertEqual(call['reasoningChars'], 4)
        self.assertEqual(waiting['llmProgress']['completedCalls'], 0)
        self.assertEqual(waiting['llmProgress']['calls'], 1)
        self.assertEqual(call['timeoutSeconds'], 10)  # Provider cap is frozen.
        self.assertIsNotNone(waiting['executionProgress']['heartbeatAt'])
        # Fault injection expires this call while the socket is still open.
        from skill_engine import write
        path = self.service.local / 'runs' / run['id'] / 'llm-progress.json'
        state = json.loads(path.read_text()); state['lastCall']['deadlineEpoch'] = time.time() - 1; write(path, state)
        done = finish(self.service, run['id'])
        self.assertEqual(done['status'], 'failed')
        self.assertIn('Model call #1 exceeded its 10s time limit', done['error'])
        self.assertEqual(done['llmProgress']['lastCall']['status'], 'failed')
        self.assertEqual(done['llmProgress']['failedCalls'], 1)
        self.assertEqual(len(MockModel.calls), 1)
        self.assertFalse(self.service.ollama.operation.locked())

    def test_disconnected_stream_does_not_complete_or_retry(self):
        MockModel.mode = 'stream-disconnect'
        done = finish(self.service, self.start()['id'])
        self.assertEqual(done['status'], 'failed')
        self.assertIn('disconnected before [DONE]', done['error'])
        self.assertEqual(done['llmProgress']['completedCalls'], 0)
        self.assertEqual(len(MockModel.calls), 1)

    def test_silent_model_has_a_real_single_call_timeout_and_no_retry(self):
        self.service.ollama.save({**self.service.ollama.state()['config'], 'inferenceTimeout': 1}, 1)
        MockModel.block = threading.Event()
        started = time.monotonic()
        run = self.service.start(registry(), 'silent', 'llm-evolution', {**self.options(), 'providerRevision': 2})
        done = finish(self.service, run['id'])
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(done['status'], 'failed')
        self.assertIn('Model call #1 exceeded its 1s time limit', done['error'])
        self.assertEqual(done['llmProgress']['completedCalls'], 0)
        self.assertEqual(done['llmProgress']['lastCall']['status'], 'failed')
        self.assertEqual(len(MockModel.calls), 1)
        self.assertFalse(self.service.ollama.operation.locked())

    def test_continuous_partial_chunks_do_not_extend_the_absolute_call_deadline(self):
        self.service.ollama.save({**self.service.ollama.state()['config'], 'inferenceTimeout': 1}, 1)
        MockModel.mode = 'stream-trickle'
        started = time.monotonic()
        run = self.service.start(registry(), 'trickle', 'llm-evolution', {**self.options(), 'providerRevision': 2})
        done = finish(self.service, run['id'])
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(done['status'], 'failed')
        self.assertIn('Model call #1 exceeded its 1s time limit', done['error'])
        self.assertGreater(done['llmProgress']['lastCall']['chunks'], 0)
        self.assertEqual(done['llmProgress']['completedCalls'], 0)
        self.assertEqual(len(MockModel.calls), 1)

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
        ollama_uri = (root / 'dist/js/ollama-ui.js').as_uri()
        self.service.ollama.save({**self.service.ollama.state()['config'], 'model': ''}, 1)
        js = f"""
import assert from 'node:assert/strict';
import {{RuntimeClient}} from {json.dumps(client_uri)};
import {{initialRegistry}} from {json.dumps(agents_uri)};
import {{OllamaUI}} from {json.dumps(ollama_uri)};
const base='http://127.0.0.1:{server.server_port}';
const client=new RuntimeClient({{fetcher:(path,options)=>fetch(base+path,options)}});
assert.equal(await client.refresh(),true);
const provider=new OllamaUI({{fetcher:(path,options)=>fetch(base+path,options),token:()=>client.capabilities.csrfToken}});
await provider.operate('reload');assert.equal(provider.data.config.model,'');
provider.edit('model','qwen3-coder:30b');
await provider.operate('save',{{...provider.data.config,model:'qwen3-coder:30b'}});
assert.equal(provider.data.config.model,'qwen3-coder:30b');
assert.match(provider.view(),/value="qwen3-coder:30b"/);
const reopened=new OllamaUI({{fetcher:(path,options)=>fetch(base+path,options)}});
await reopened.operate('reload');assert.equal(reopened.data.config.model,'qwen3-coder:30b');
await client.warmModel();
const preloadDeadline=Date.now()+30000;
while(Date.now()<preloadDeadline){{
  assert.equal(await client.refresh(),true,client.error);
  if(client.data.provider.warmup.status!=='RUNNING')break;
  await new Promise(resolve=>setTimeout(resolve,250));
}}
assert.equal(client.data.provider.warmup.status,'PRELOAD_PASS');
assert.equal(client.data.provider.warmup.config.model,'qwen3-coder:30b');
client.llmSeconds=60;await client.startLlm(initialRegistry());
const workflowDeadline=Date.now()+(client.llmSeconds+10)*1000;
while(Date.now()<workflowDeadline){{
  assert.equal(await client.refresh(),true,client.error);
  if(client.data.llm.latestRun.status==='completed')break;
  if(['failed','cancelled','interrupted'].includes(client.data.llm.latestRun.status))break;
  await new Promise(resolve=>setTimeout(resolve,250));
}}
assert.equal(client.data.llm.latestRun.status,'completed');
assert.equal(client.data.llm.latestRun.llmResult.calls,15);
assert.equal(client.data.llm.latestRun.llmConfig.provider.config.model,'qwen3-coder:30b');
assert.equal(client.data.llm.latestRun.llmConfig.provider.revision,reopened.data.revision);
await client.selectLlmRun(client.data.llm.latestRun.id);
await client.approveLlm(client.data.llm.latestRun.id);
assert.equal(client.data.llm.active.label,'L1');
await client.activateLlm('LSV-baseline');
assert.equal(client.data.llm.activeVersionId,'LSV-baseline');
assert.equal(client.data.skills.activeVersionId,'SKV-baseline');
console.log(JSON.stringify({{polls:client.pollCount,status:'PASS'}}));
"""
        try:
            # Bounded outer harness covers preload, workflow and evidence replay.
            result = subprocess.run([node['path'], '--input-type=module', '-e', js], capture_output=True, text=True, timeout=130)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'PASS')
            self.assertEqual(len(MockModel.calls), 15)
            self.assertTrue(all(call['model'] == 'qwen3-coder:30b' for call in MockModel.calls))
            self.assertEqual(MockModel.warmups, [{'model':'qwen3-coder:30b','prompt':'','stream':False,'keep_alive':'15m'}])
            llm_logs=self.service.logs.list(module='llm')
            self.assertEqual(sum('started' in r['message'] for r in llm_logs['records']),15)
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
