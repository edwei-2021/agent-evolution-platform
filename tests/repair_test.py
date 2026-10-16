"""Trusted evaluator and actual pinned SDK workflow tests; loopback model only."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from functools import partial
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from repair_fixture import BASELINE, HIDDEN, validate_source
from adaptive_validation import current as validation_calibration
from validation_wait import first_request, startup_budget, repair_workflow_seconds
from repair_engine import trusted_test, verify
from runtime_service import RuntimeService,ROLES
from ollama_bridge import DEFAULTS
from serve_gui import GuiHandler,DIST

GOOD='def clamp(value, lower, upper):\n    if lower > upper:\n        raise ValueError("invalid bounds")\n    return max(lower, min(value, upper))\n'
# Valid exception-class spelling used by real tool-calling models.
BARE='def clamp(value, lower, upper):\n    if lower > upper:\n        raise ValueError\n    return max(lower, min(value, upper))'
try:SDK=importlib.metadata.version('nanobot-ai')=='0.3.5'
except importlib.metadata.PackageNotFoundError:SDK=False

class EvaluatorTests(unittest.TestCase):
    def test_exception_class_and_instance_forms_pass_independent_tests(self):
        for expression in ('ValueError', 'ValueError()', 'ValueError("invalid bounds")'):
            source=BARE.replace('raise ValueError', 'raise '+expression)
            for split in ('visible','hidden'):
                with self.subTest(expression=expression,split=split):
                    self.assertEqual(trusted_test(source,split)['passed'],6)
    def test_exception_syntax_rejects_other_types_chaining_and_shadowing(self):
        for expression in ('', 'TypeError', 'TypeError()', 'min', 'None',
                           'ValueError from None', 'ValueError() from ValueError()',
                           'ValueError.__class__', 'ValueError(message="bounds")'):
            with self.subTest(expression=expression),self.assertRaises((ValueError,SyntaxError)):
                validate_source(BARE.replace('raise ValueError','raise '+expression))
        with self.assertRaisesRegex(ValueError,'Cannot replace trusted builtins'):
            validate_source(BARE.replace('    if lower > upper:', '    ValueError = lower\n    if lower > upper:'))
    def test_independent_visible_hidden_scores_and_baseline_failures(self):
        self.assertLess(trusted_test(BASELINE,'visible')['passed'],6)
        for split in ('visible','hidden'):self.assertEqual(trusted_test(GOOD,split)['passed'],6)
    def test_unsafe_python_cannot_run_or_change_trusted_tests(self):
        for source in ['import os\n'+GOOD,GOOD+'open("outside","w")',
                       'def clamp(value, lower, upper):\n    return value.__class__\n',
                       'def clamp(value, lower, upper):\n    while True:\n        pass\n',
                       'def clamp(value, lower, upper):\n    return clamp(value,lower,upper)\n',
                       'def clamp(value, lower, upper):\n    return 2**1000000\n']:
            with self.subTest(source=source[:50]),self.assertRaises((ValueError,SyntaxError)):validate_source(source)
    def test_invalid_budgets_and_missing_sdk_fail_before_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            service=RuntimeService(root)
            try:
                service.ollama.save({**DEFAULTS,'host':'127.0.0.1','port':1,'model':'not-dispatched:1'},0)
                base={'maxSeconds':60,'callTimeoutSeconds':10,'callBudget':8,'providerRevision':1}
                for change in [{'callBudget':True},{'callBudget':13},{'maxSeconds':59},{'callTimeoutSeconds':9}]:
                    with self.assertRaises(ValueError):service.repair.freeze({**base,**change})
                if not SDK:
                    with self.assertRaises(RuntimeError):service.repair.freeze(base)
                self.assertFalse(service.ollama.operation.locked())
            finally:service.close()

class Model(BaseHTTPRequestHandler):
    calls=[];mode='good';gate=None;entered=threading.Event()
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.calls.append(body);self.entered.set()
        if self.gate:self.gate.wait(10)
        n=len(self.calls);name,args=None,None
        if self.mode=='http-error':
            raw=b'{"error":"mock unavailable"}';self.send_response(503);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        if self.mode=='claim':content='All tests passed; no changes needed.'
        elif self.mode=='budget':name,args='read_solution',{'path':'solution.py'};content=None
        elif self.mode=='escape':name,args='read_solution',{'path':'../outside'};content=None
        elif n==1:name,args='read_solution',{'path':'solution.py'};content=None
        elif n==2:name,args='write_solution',{'path':'solution.py','source':BARE if self.mode=='bare' else GOOD.replace('\n','\r\n') if self.mode=='crlf' else GOOD};content=None
        elif n==3:name,args='run_tests',{};content=None
        else:content='Implemented inclusive bounds and ValueError for reversed bounds.'
        message={'role':'assistant','content':content};finish='stop'
        if name:message['tool_calls']=[{'id':f'call_{n}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}];finish='tool_calls'
        reply={'model':body['model'],'choices':[{'message':message,'finish_reason':finish}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
        if self.mode=='stream':
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            if name:
                call=message['tool_calls'][0];argument=call['function']['arguments'];half=len(argument)//2
                deltas=[{'tool_calls':[{'index':0,'id':call['id'],'type':'function','function':{'name':name,'arguments':argument[:half]}}]},
                        {'tool_calls':[{'index':0,'function':{'arguments':argument[half:]}}]}]
            else:deltas=[{'content':content}]
            for i,delta in enumerate(deltas):
                event={'model':body['model'],'choices':[{'index':0,'delta':delta,'finish_reason':finish if i==len(deltas)-1 else None}]}
                self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');return
        raw=json.dumps(reply).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass

@unittest.skipUnless(SDK,'Pinned SDK integration requires the optional nanobot environment')
class SdkWorkflowTests(unittest.TestCase):
    def setUp(self):
        io_seconds=validation_calibration()['perCallIoAllowanceSeconds']
        self.workflow_seconds=repair_workflow_seconds(io_seconds)
        self.startup_seconds=startup_budget(io_seconds,self.workflow_seconds)
        Model.calls=[];Model.mode='good';Model.gate=None;Model.entered.clear()
        self.temp=tempfile.TemporaryDirectory();self.service=RuntimeService(self.temp.name)
        self.model=ThreadingHTTPServer(('127.0.0.1',0),Model);self.thread=threading.Thread(target=self.model.serve_forever,daemon=True);self.thread.start()
        self.service.ollama.save({**DEFAULTS,'host':'127.0.0.1','port':self.model.server_port,'model':'mock-qwen:local','inferenceTimeout':10,'maxTokens':512},0)
    def tearDown(self):
        if Model.gate:Model.gate.set()
        self.service.close();self.model.shutdown();self.model.server_close();self.thread.join();self.temp.cleanup()
    def start(self,budget=8):
        registry={'agents':[{'id':'AG-'+str(i),'name':r,'role':r,'enabled':True} for i,r in enumerate(ROLES)]}
        return self.service.start(registry,'repair','nanobot-repair',{'maxSeconds':self.workflow_seconds,'callTimeoutSeconds':10,'callBudget':budget,'providerRevision':1})
    def finish(self,id):
        deadline=time.monotonic()+self.workflow_seconds+15
        next_report=time.monotonic()+10
        while time.monotonic()<deadline:
            run=self.service.get_run(id)
            if run['status'] in ('completed','failed','cancelled','interrupted'):return run
            if time.monotonic()>=next_report:
                print(f'REPAIR_TEST_PROGRESS elapsed_seconds={self.workflow_seconds+15-round(deadline-time.monotonic())} '
                      f'role={next((a["role"] for a in run["agents"] if a["status"]=="running"),"queued")} '
                      f'calls={(run.get("repairProgress") or {}).get("completedCalls",0)}',flush=True)
                next_report=time.monotonic()+10
            time.sleep(.025)
        self.fail('SDK workflow did not terminate')
    def test_real_sdk_repair_tools_independent_scores_and_evidence(self):
        run=self.start();done=self.finish(run['id']);self.assertEqual(done['status'],'completed',done)
        self.assertTrue(done['repairResult']['repairPassed']);self.assertEqual(done['repairResult']['calls'],4)
        self.assertEqual(done['repairResult']['toolCalls'],3);self.assertEqual(done['repairResult']['candidate']['hidden']['passed'],6)
        self.assertEqual(len(Model.calls),4);self.assertFalse(self.service.ollama.operation.locked())
        self.assertTrue(all(sorted(t['function']['name'] for t in c['tools'])==['read_solution','run_tests','write_solution'] for c in Model.calls[:-1]))
        self.assertEqual(Model.calls[-1]['tools'],[])
        self.assertTrue(all(c['model']=='mock-qwen:local' and c['temperature']==0 for c in Model.calls))
        for inputs,_ in HIDDEN:self.assertNotIn(json.dumps(inputs),json.dumps(Model.calls))
        directory=self.service.local/'runs'/run['id'];self.assertEqual(verify(directory),done['repairResult'])
        sdk=json.loads((directory/'repair-sdk-result.json').read_text());self.assertEqual(sdk['sdkVersion'],'0.3.5');self.assertEqual(sdk['stopReason'],'completed')
        self.assertEqual(self.service.llm.snapshot()['activeVersionId'],'LSV-baseline')
        tools=json.loads((directory/'repair-tools.json').read_text());tools[1]['arguments']['source']=BASELINE
        (directory/'repair-tools.json').write_text(json.dumps(tools))
        with self.assertRaises(ValueError):verify(directory)
    def test_recorded_bare_valueerror_candidate_completes_actual_sdk_and_review(self):
        Model.mode='bare';done=self.finish(self.start(8)['id'])
        self.assertEqual(done['status'],'completed',done)
        result=done['repairResult']
        self.assertTrue(result['repairPassed'])
        self.assertEqual((result['calls'],result['toolCalls']),(4,3))
        self.assertEqual([result['candidate'][s]['passed'] for s in ('visible','hidden')],[6,6])
        directory=self.service.local/'runs'/done['id']
        self.assertEqual((directory/'repair-candidate.py').read_text(),BARE)
        self.assertEqual(json.loads((directory/'repair-sdk-result.json').read_text())['stopReason'],'completed')
        tools=json.loads((directory/'repair-tools.json').read_text())
        self.assertEqual([t['name'] for t in tools],['read_solution','write_solution','run_tests'])
        self.assertTrue(all(t['status']=='completed' for t in tools))
        self.assertEqual(verify(directory),result)
        self.assertFalse(self.service.ollama.operation.locked())
    def test_fragmented_sse_tool_arguments_reconstruct_and_tampering_is_rejected(self):
        Model.mode='stream';run=self.start();done=self.finish(run['id']);self.assertEqual(done['status'],'completed',done)
        directory=self.service.local/'runs'/run['id'];calls=json.loads((directory/'repair-calls.json').read_text())
        self.assertTrue(calls[1]['streamEvents']);self.assertGreater(calls[1]['toolArgumentChars'],0)
        calls[1]['streamEvents'][0]['choices'][0]['delta']['tool_calls'][0]['function']['arguments']='tampered'
        (directory/'repair-calls.json').write_text(json.dumps(calls))
        with self.assertRaises(ValueError):verify(directory)
    def test_crlf_source_replay_preserves_candidate_bytes(self):
        Model.mode='crlf';run=self.start();done=self.finish(run['id']);self.assertEqual(done['status'],'completed',done)
        directory=self.service.local/'runs'/run['id']
        self.assertIn(b'\r\n',(directory/'repair-candidate.py').read_bytes())
        self.assertEqual(verify(directory),done['repairResult'])
    def test_agent_claim_does_not_replace_test_evidence(self):
        Model.mode='claim';done=self.finish(self.start()['id'])
        self.assertEqual(done['status'],'completed',done);self.assertFalse(done['repairResult']['repairPassed']);self.assertEqual(len(Model.calls),1)
    def test_http_errors_have_no_sdk_retry(self):
        Model.mode='http-error';done=self.finish(self.start()['id'])
        self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),1);self.assertFalse(self.service.ollama.operation.locked())
    def test_model_call_budget_is_an_absolute_dispatch_cap(self):
        Model.mode='budget';done=self.finish(self.start(2)['id'])
        self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),2)
    def test_cancellation_stops_the_actual_sdk_worker_and_later_calls(self):
        Model.gate=threading.Event();run=self.start()
        first_request(Model.entered,self.service,run['id'],self.startup_seconds,label='repair-cancel')
        with self.assertRaises(RuntimeError):self.service.ollama.start_warmup(1)
        self.service.cancel(run['id']);done=self.finish(run['id'])
        self.assertEqual(done['status'],'cancelled');self.assertEqual(len(Model.calls),1);self.assertFalse(self.service.ollama.operation.locked())
    def test_single_call_deadline_terminates_sdk_and_prevents_more_dispatches(self):
        self.service.ollama.save({**self.service.ollama.state()['config'],'inferenceTimeout':1},1)
        registry={'agents':[{'id':'AG-'+str(i),'name':r,'role':r,'enabled':True} for i,r in enumerate(ROLES)]}
        Model.gate=threading.Event()
        run=self.service.start(registry,'timeout','nanobot-repair',{'maxSeconds':self.workflow_seconds,'callTimeoutSeconds':10,'callBudget':8,'providerRevision':2})
        done=self.finish(run['id']);self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),1)
        self.assertEqual(done['repairProgress']['failedCalls'],1);self.assertFalse(self.service.ollama.operation.locked())
    def test_actual_javascript_client_runs_api_reads_verified_patch_and_has_no_approval_path(self):
        from repair_runtime import sdk_status
        self.assertTrue(sdk_status(self.service.root)['available'])  # explicit SDK preflight
        import subprocess
        from setup_wsl import find_node
        node=find_node()
        if not node:self.skipTest('Linux Node required for transport integration')
        class Quiet(GuiHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));server.runtime=self.service
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        root=Path(__file__).resolve().parents[1]
        js=f"""
import assert from 'node:assert/strict';
import {{RuntimeClient}} from {json.dumps((root/'dist/js/runtime-client.js').as_uri())};
import {{initialRegistry}} from {json.dumps((root/'dist/js/agents.js').as_uri())};
const base='http://127.0.0.1:{server.server_port}';
const client=new RuntimeClient({{fetcher:(path,options)=>fetch(base+path,options)}});
assert.equal(await client.refresh(),true);assert.equal(client.data.repair.sdk.available,true);
client.repairSeconds={self.workflow_seconds};client.repairCallSeconds=10;await client.startRepair(initialRegistry());
const deadline=Date.now()+({self.workflow_seconds}+15)*1000;
while(Date.now()<deadline){{assert.equal(await client.refresh(),true,client.error);if(['completed','failed'].includes(client.data.repair.latestRun.status))break;await new Promise(r=>setTimeout(r,100));}}
const run=client.data.repair.latestRun;assert.equal(run.status,'completed');assert.equal(run.repairResult.repairPassed,true);
await client.readRepairEvidence(run.id);assert.match(client.repairEvidence.patch,/ValueError/);assert.equal(client.repairEvidence.tools.length,3);
console.log('SDK API client PASS');
"""
        try:
            print(f'REPAIR_JS_EXPECTED workflow_limit_seconds={self.workflow_seconds} node_limit_seconds={self.workflow_seconds+30}',flush=True)
            result=subprocess.run([node['path'],'--input-type=module','-e',js],text=True,capture_output=True,timeout=self.workflow_seconds+30)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(Model.calls),4)
            with self.assertRaises(RuntimeError):self.service.llm.approve(self.service.snapshot()['repair']['latestRun']['id'],1)
        finally:server.shutdown();server.server_close();thread.join()
