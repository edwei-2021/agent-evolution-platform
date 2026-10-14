"""Real GEPA + nanobot integration with loopback model and trusted evaluators."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from functools import partial
import faulthandler
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gepa_dataset import dataset, GROUPS, skill
from adaptive_validation import current as validation_calibration
from gepa_validation_budget import smoke_budget
from validation_wait import first_request, startup_budget
from gepa_engine import verify
from repair_engine import trusted_test
from runtime_service import RuntimeService, ROLES
from ollama_bridge import DEFAULTS
from serve_gui import GuiHandler, DIST
try:SDK=importlib.metadata.version('nanobot-ai')=='0.3.5' and importlib.metadata.version('gepa')=='0.1.4'
except importlib.metadata.PackageNotFoundError:SDK=False

IMPROVED='VERIFIED_WORKFLOW: Read the requested contract and source, implement all boundary cases, run visible tests, then summarize. Preserve the signature and use only granted tools.'
def source(task):
    k=task['offset'];g=task['group'];head='def clamp(value, lower, upper):\n'
    expressions={'absolute-offset':'max(value-lower,lower-value)+upper','minimum':'min(value,lower,upper)',
      'maximum':'max(value,lower,upper)','sign':'(-1 if value < 0 else 1 if value > 0 else 0)',
      'positive-sum':'max(0,value)+max(0,lower)+max(0,upper)','distance':'max(value-upper,upper-value)',
      'threshold':'(lower if value < upper else upper)'}
    if g in ('clamp','span'):head+='    if lower > upper:\n        raise ValueError("bounds")\n';expression='max(lower,min(value,upper))' if g=='clamp' else 'upper-lower'
    elif g=='clipped-sum':head+='    if upper <= 0:\n        raise ValueError("limit")\n';expression='max(-upper,min(value+lower,upper))'
    else:expression=expressions[g]
    return head+'    return '+expression+f'+({k})\n'

class DatasetTests(unittest.TestCase):
    def test_grouped_dataset_counts_and_golden_reference_sources(self):
        full=dataset('full');self.assertEqual([len(full[k]) for k in ('train','validation','heldout')],[20,10,20])
        smoke=dataset('smoke');self.assertEqual([len(smoke[k]) for k in ('train','validation','heldout')],[4,2,4])
        sets=[set(GROUPS[s]) for s in GROUPS]
        self.assertTrue(all(not sets[i]&sets[j] for i in range(3) for j in range(i)))
        for split,rows in full.items():
            for task in rows:
                for part in ('visible','hidden'):
                    with self.subTest(task=task['id'],split=part):self.assertEqual(trusted_test(source(task),part,task['fixture'])['passed'],3)
        self.assertEqual(skill('Changed body')['name'],'python-fix-and-verify')
        with self.assertRaises(ValueError):skill('x'*8001)
    def test_options_reject_invalid_limits_revisions_and_missing_sdk_before_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            service=RuntimeService(root)
            try:
                service.ollama.save({**DEFAULTS,'host':'127.0.0.1','port':1,'model':'local'},0)
                base={'profile':'smoke','maxSeconds':60,'callTimeoutSeconds':10,'taskCallBudget':6,'metricBudget':8,'proposalBudget':2,'providerRevision':1,'expectedRevision':1}
                for change in [{'metricBudget':True},{'metricBudget':5},{'proposalBudget':9},{'taskCallBudget':13},{'profile':'fake'}]:
                    with self.assertRaises(ValueError):service.gepa.freeze({**base,**change})
                with self.assertRaises(RuntimeError):service.gepa.freeze({**base,'expectedRevision':2})
                if not SDK:
                    with self.assertRaises(RuntimeError):service.gepa.freeze(base)
                self.assertFalse(service.ollama.operation.locked())
            finally:service.close()

class Model(BaseHTTPRequestHandler):
    calls=[];mode='good';gate=None;entered=threading.Event()
    def log_message(self,*args):pass
    def should_repair(self,messages):
        marker='VERIFIED_WORKFLOW' in str(messages)
        match=re.search(r'Task ID: (PY-[a-z-]+-\d+)',str(messages))
        final=match and match[1] in {t['id'] for t in dataset('smoke')['heldout']}
        return self.mode=='perfect' or (not marker if self.mode=='regression' and final else marker)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.calls.append(body);self.entered.set()
        if self.gate:self.gate.wait(10)
        if self.mode=='http-error':
            raw=b'{"error":"mock unavailable"}';self.send_response(503);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        messages=body['messages'];message={'role':'assistant','content':'No changes needed; tests passed.'}
        if not body['tools']:
            value={'skill_body':IMPROVED} if self.mode!='bad-proposal' else {'name':'mutated','skill_body':IMPROVED}
            message['content']=json.dumps(value)
        elif self.should_repair(messages):
            identifier=re.search(r'Task ID: (PY-[a-z-]+-\d+)',str(messages))[1]
            task=next(t for rows in dataset('smoke').values() for t in rows if t['id']==identifier)
            used=sum(m.get('role')=='tool' for m in messages)
            name,args=[('read_solution',{'path':'solution.py'}),('write_solution',{'path':'solution.py','source':source(task)}),('run_tests',{})][used] if used<3 else (None,None)
            if name:message={'role':'assistant','content':None,'tool_calls':[{'id':f'c{used}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        reply={'model':body['model'],'choices':[{'message':message,'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
        if self.mode=='stream':
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            if 'tool_calls' in message:
                call=message['tool_calls'][0];argument=call['function']['arguments'];half=len(argument)//2
                deltas=[{'tool_calls':[{'index':0,'id':call['id'],'type':'function','function':{'name':call['function']['name'],'arguments':argument[:half]}}]}, {'tool_calls':[{'index':0,'function':{'arguments':argument[half:]}}]}]
            else:
                text=message['content'];half=len(text)//2;deltas=[{'content':text[:half]},{'content':text[half:]}]
            for i,delta in enumerate(deltas):
                event={'model':body['model'],'choices':[{'index':0,'delta':delta,'finish_reason':reply['choices'][0]['finish_reason'] if i==len(deltas)-1 else None}]}
                self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode());self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');return
        raw=json.dumps(reply).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass

@unittest.skipUnless(SDK,'Pinned GEPA and nanobot environment required')
class GepaWorkflowTests(unittest.TestCase):
    def setUp(self):
        # Include serial GEPA search and final rollouts before freezing the run.
        io_seconds = validation_calibration()['perCallIoAllowanceSeconds']
        self.workflow_seconds = smoke_budget(io_seconds)['workflowSeconds']
        self.startup_seconds = startup_budget(io_seconds, self.workflow_seconds)
        Model.calls=[];Model.mode='good';Model.gate=None;Model.entered.clear()
        self.temp=tempfile.TemporaryDirectory();self.service=RuntimeService(self.temp.name)
        self.model=ThreadingHTTPServer(('127.0.0.1',0),Model);self.thread=threading.Thread(target=self.model.serve_forever,daemon=True);self.thread.start()
        self.service.ollama.save({**DEFAULTS,'host':'127.0.0.1','port':self.model.server_port,'model':'mock-gepa:local','inferenceTimeout':10,'maxTokens':512},0)
    def tearDown(self):
        result=getattr(getattr(self,'_outcome',None),'result',None)
        failed=result is not None and any(test is self for test,_ in result.failures+result.errors)
        support=None
        if failed:
            report_root=Path(os.environ.get('AEP_TEST_REPORT_DIR',
                str(Path(__file__).resolve().parents[1]/'.local/test-reports')))
            support=report_root/'failure-evidence'/'gepa_test'/(
                self._testMethodName+'-'+uuid.uuid4().hex)
            try:
                support.mkdir(parents=True)
                with self.service.lock:
                    run=self.service.current or {}
                    roles=[{key:agent.get(key) for key in ('role','status','pid','exitCode','error','updatedAt')}
                           for agent in run.get('agents',[])]
                    run_id=run.get('id')
                    status=run.get('status')
                progress_path=self.service.local/'runs'/str(run_id)/'gepa-progress.json'
                try:
                    progress=json.loads(progress_path.read_text())
                except (OSError,ValueError):
                    progress={}
                last=progress.get('lastCall') or {}
                diagnostic={'test':self.id(),'capturedAtEpoch':time.time(),
                    'runId':run_id,'runStatus':status,'roles':roles,
                    'workflowLimitSeconds':(run.get('gepaConfig') or {}).get('maxSeconds'),
                    'workflowDeadlineEpoch':(run.get('gepaConfig') or {}).get('deadlineEpoch'),
                    'phase':progress.get('phase'),'activeRollout':progress.get('activeRollout'),
                    'activeTask':progress.get('activeTask'),'modelRequestsReceived':len(Model.calls),
                    'verification':progress.get('verification'),
                    'lastCall':{key:last.get(key) for key in
                                ('id','kind','status','startedAt','deadlineEpoch','timeoutSeconds')},
                    'supervisorThreadAlive':bool(self.service.thread and self.service.thread.is_alive())}
                (support/'diagnostic.json').write_text(json.dumps(diagnostic,indent=2))
                with (support/'threads.log').open('w') as stream:
                    faulthandler.dump_traceback(file=stream,all_threads=True)
            except (OSError,ValueError,RuntimeError) as exc:
                print(f'GEPA_TEST_SUPPORT_ERROR {type(exc).__name__}: {exc}',flush=True)
        if Model.gate:Model.gate.set()
        try:
            self.service.close();self.model.shutdown();self.model.server_close();self.thread.join()
        finally:
            if support and support.is_dir():
                try:
                    shutil.copytree(self.temp.name,support/'run')
                    print(f'GEPA_TEST_SUPPORT {support}',flush=True)
                except (OSError,shutil.Error) as exc:
                    print(f'GEPA_TEST_SUPPORT_ERROR {type(exc).__name__}: {exc}',flush=True)
            self.temp.cleanup()
    def start(self,**changes):
        options={'profile':'smoke','maxSeconds':self.workflow_seconds,'callTimeoutSeconds':10,'taskCallBudget':6,'metricBudget':8,'proposalBudget':2,'providerRevision':1,'expectedRevision':1,**changes}
        registry={'agents':[{'id':'AG-'+str(i),'name':r,'role':r,'enabled':True} for i,r in enumerate(ROLES)]}
        return self.service.start(registry,'gepa','gepa-evolution',options)
    def finish(self,identifier):
        deadline=time.monotonic()+self.workflow_seconds+30
        next_report=time.monotonic()+10
        while time.monotonic()<deadline:
            run=self.service.get_run(identifier)
            if run['status'] in ('completed','failed','cancelled','interrupted'):return run
            if time.monotonic()>=next_report:
                progress=run.get('gepaProgress') or {}
                print(f'GEPA_TEST_PROGRESS role={next((a["role"] for a in run["agents"] if a["status"]=="running"), "queued")} '
                      f'phase={progress.get("phase")} rollouts={progress.get("rollouts", 0)} '
                      f'active_rollout={progress.get("activeRollout")}',flush=True)
                next_report=time.monotonic()+10
            time.sleep(.04)
        self.fail('GEPA workflow did not terminate')
    def test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate(self):
        Model.mode='stream';run=self.start();done=self.finish(run['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        result=done['gepaResult'];self.assertTrue(result['eligible']);self.assertEqual(result['gepaVersion'],'0.1.4');self.assertLessEqual(result['metricEvaluations'],8)
        self.assertEqual(result['final']['selected']['validation'],{'passed':2,'total':2});self.assertEqual(result['final']['selected']['heldout'],{'passed':4,'total':4})
        from step_trace import snapshot as steps_snapshot
        steps=steps_snapshot(self.service,done['id'])['steps']
        self.assertTrue({'search','final-evaluation','role.process','trusted-tests.batch','sdk.turn','model.call','tool.execute'}<={s['name'] for s in steps})
        self.assertTrue(all(s['status']=='completed' for s in steps))
        self.assertEqual(result['calls'],len(Model.calls));self.assertFalse(self.service.ollama.operation.locked())
        self.assertEqual(self.service.gepa.snapshot()['activeVersionId'],'GSV-baseline');self.assertEqual(self.service.llm.snapshot()['activeVersionId'],'LSV-baseline')
        directory=self.service.local/'runs'/run['id'];self.assertEqual(verify(directory),result)
        replay=json.loads((directory/'gepa-progress.json').read_text())['verification']
        self.assertEqual((replay['verifiedRollouts'],replay['totalRollouts']),
                         (result['rollouts'],result['rollouts']))
        selection=json.loads((directory/'gepa-selection.json').read_text());ledger=json.loads((directory/'gepa-rollouts.json').read_text())
        final_ids={t['id'] for t in dataset('smoke')['heldout']}
        self.assertFalse(any(r['taskId'] in final_ids and r['stage']=='search' for r in ledger))
        self.assertTrue(all(r['startedAt']>=selection['frozenAt'] for r in ledger if r['stage']!='search'))
        reflection=[c for c in Model.calls if not c['tools']];self.assertEqual(len(reflection),result['proposals'])
        for c in reflection:
            raw=json.dumps(c)
            for t in dataset('smoke')['validation']+dataset('smoke')['heldout']:self.assertNotIn(t['id'],raw)
        approved=self.service.gepa.approve(run['id'],1);self.assertEqual(approved['revision'],2);self.assertNotEqual(approved['activeVersionId'],'GSV-baseline')
        with self.assertRaises(RuntimeError):self.service.gepa.approve(run['id'],2)
        rollback=self.service.gepa.activate('GSV-baseline',2);self.assertEqual(rollback['revision'],3)
        with self.assertRaises(RuntimeError):self.service.gepa.activate(approved['activeVersionId'],2)
        # Corrupt final data after review: approval must re-evaluate, not trust a boolean.
        ledger[-1]['score']=0;(directory/'gepa-rollouts.json').write_text(json.dumps(ledger))
        with self.assertRaises(ValueError):self.service.gepa.approve(run['id'],3)
    def test_perfect_seed_skips_proposals_and_cannot_release_without_improvement(self):
        Model.mode='perfect';done=self.finish(self.start()['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        self.assertFalse(done['gepaResult']['eligible']);self.assertEqual(done['gepaResult']['proposals'],0)
        self.assertLessEqual(done['gepaResult']['metricEvaluations'],8)
        with self.assertRaises(RuntimeError):self.service.gepa.approve(done['id'],1)
    def test_http_failure_is_one_request_and_releases_shared_provider_slot(self):
        Model.mode='http-error';done=self.finish(self.start()['id']);self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),1)
        self.assertFalse(self.service.ollama.operation.locked());self.assertNotIn('gepaResult',done)
    def test_bad_proposal_cannot_mutate_metadata_or_start_final_tasks(self):
        Model.mode='bad-proposal';done=self.finish(self.start()['id']);self.assertEqual(done['status'],'failed',done)
        directory=self.service.local/'runs'/done['id'];ledger=json.loads((directory/'gepa-rollouts.json').read_text());self.assertTrue(all(r['stage']=='search' for r in ledger))
        self.assertFalse((directory/'gepa-selection.json').exists());self.assertEqual(self.service.gepa.snapshot()['revision'],1)
    def test_per_task_iteration_limit_prevents_extra_model_calls(self):
        Model.mode='perfect';done=self.finish(self.start(taskCallBudget=2)['id']);self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),2)
        self.assertFalse(self.service.ollama.operation.locked())
    def test_global_call_budget_is_enforced_before_next_request(self):
        original=self.service.gepa.freeze
        self.service.gepa.freeze=lambda options:{**original(options),'callBudget':1}
        done=self.finish(self.start()['id']);self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),1)
    def test_cancel_stops_actual_gepa_sdk_process(self):
        Model.gate=threading.Event();run=self.start()
        first_request(Model.entered,self.service,run['id'],self.startup_seconds,label='gepa-cancel')
        with self.assertRaises(RuntimeError):self.service.ollama.start_warmup(1,15)
        self.service.cancel(run['id']);done=self.finish(run['id']);self.assertEqual(done['status'],'cancelled');self.assertFalse(self.service.ollama.operation.locked())
        directory=self.service.local/'runs'/run['id'];calls=json.loads((directory/'gepa-calls.json').read_text());self.assertEqual(calls[-1]['status'],'cancelled')
    def test_heldout_regression_blocks_release_even_with_validation_improvement(self):
        Model.mode='regression';done=self.finish(self.start()['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        result=done['gepaResult'];self.assertGreater(result['final']['selected']['validation']['passed'],result['final']['baseline']['validation']['passed'])
        self.assertLess(result['final']['selected']['heldout']['passed'],result['final']['baseline']['heldout']['passed']);self.assertFalse(result['eligible'])
        with self.assertRaises(RuntimeError):self.service.gepa.approve(done['id'],1)
    def test_call_deadline_stops_silent_response_and_finalizes_global_evidence(self):
        Model.gate=threading.Event();original=self.service.gepa.freeze
        self.service.gepa.freeze=lambda options:{**original(options),'callTimeoutSeconds':1}
        done=self.finish(self.start()['id']);self.assertEqual(done['status'],'failed');self.assertEqual(len(Model.calls),1)
        self.assertFalse(self.service.ollama.operation.locked())
        path=self.service.local/'runs'/done['id']/'gepa-calls.json';self.assertEqual(json.loads(path.read_text())[-1]['status'],'failed')
    def test_actual_js_client_to_python_api_dispatch_and_result_validation(self):
        from gepa_runtime import gepa_status
        readiness=gepa_status(self.service.root)  # explicit pinned SDK preflight
        self.assertTrue(readiness['available'],readiness)
        from setup_wsl import find_node
        class QuietHandler(GuiHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(DIST))); server.runtime=self.service
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            script="""import {RuntimeClient,validateGepaRun} from './dist/js/runtime-client.js';
import {initialRegistry} from './dist/js/agents.js';
const base=process.argv[1],client=new RuntimeClient({fetcher:(p,o)=>fetch(base+p,o)});
await client.refresh();client.gepaSeconds=Number(process.argv[2]);await client.startGepa(initialRegistry());
const deadline=Date.now()+(Number(process.argv[2])+20)*1000;
while(Date.now()<deadline){await client.refresh();const run=client.data?.gepa?.latestRun;if(run&&['completed','failed'].includes(run.status)){validateGepaRun(run);console.log(JSON.stringify({status:run.status,eligible:run.gepaResult?.eligible}));process.exit(run.status==='completed'?0:2);}await new Promise(r=>setTimeout(r,50));}process.exit(3);"""
            command=[find_node()['path'], '--input-type=module','-e',script,
                     f'http://127.0.0.1:{server.server_port}',str(self.workflow_seconds)]
            print(f'GEPA_TEST_EXPECTED case=js-client maximum_workflow_seconds={self.workflow_seconds} '
                  f'node_timeout_seconds={self.workflow_seconds+30}',flush=True)
            with subprocess.Popen(command,cwd=DIST.parent,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,text=True) as node:
                started=time.monotonic();next_report=started+10
                while True:
                    try:
                        stdout,stderr=node.communicate(timeout=min(10,max(0.1,self.workflow_seconds+30-(time.monotonic()-started))))
                        break
                    except subprocess.TimeoutExpired:
                        elapsed=time.monotonic()-started
                        if elapsed>=self.workflow_seconds+30:
                            node.kill();stdout,stderr=node.communicate()
                            self.fail(f'JS client exceeded calibrated workflow budget: {elapsed:.1f}s; '
                                      f'stdout={stdout[-500:]} stderr={stderr[-500:]}')
                        if time.monotonic()>=next_report:
                            with self.service.lock:
                                identifier=(self.service.current or {}).get('id')
                            run=self.service.get_run(identifier) if identifier else {}
                            progress=run.get('gepaProgress') or {}
                            verification=progress.get('verification') or {}
                            print(f'GEPA_TEST_PROGRESS case=js-client elapsed_seconds={int(elapsed)} '
                                  f'role={next((a["role"] for a in run.get("agents",[]) if a["status"]=="running"), "queued")} '
                                  f'phase={progress.get("phase")} rollouts={progress.get("rollouts",0)} '
                                  f'active_rollout={progress.get("activeRollout")} '
                                  f'review_verified={verification.get("verifiedRollouts",0)}/{verification.get("totalRollouts",0)}',flush=True)
                            next_report=time.monotonic()+10
                result=subprocess.CompletedProcess(command,node.returncode,stdout,stderr)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout);self.assertTrue(json.loads(result.stdout)['eligible'])
        finally:server.shutdown();server.server_close();worker.join()
