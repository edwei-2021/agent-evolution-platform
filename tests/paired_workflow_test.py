"""Real SDK net-gain regression, final replay, UI rejection and approval gate."""
import copy
import json
import re
import subprocess
import unittest
from unittest.mock import patch
import challenge_workflow_test as fixture
from gepa_comparison import POLICY


def net_gain_model(handler):
    body=json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
    fixture.Model.calls.append(body)
    messages=body['messages']
    if messages[0]['content']==fixture.REFLECTION_SYSTEM:
        message={'role':'assistant','content':json.dumps({'skill_body':fixture.IMPROVED})}
    else:
        task_id=re.search(r'Task ID: (CH-[A-Za-z0-9-]+)',str(messages))[1]
        selected=fixture.IMPROVED in str(messages)
        first=task_id in ('CH-balanced-brackets','CH-run-length-encode')
        should_repair=not first if selected else first
        steps=[('read_solution',{'path':'solution.py'}),
               ('write_solution',{'path':'solution.py','source':fixture.BY_ID[task_id]['reference']}),
               ('run_tests',{})]
        used=sum(m.get('role')=='tool' for m in messages)
        message={'role':'assistant','content':'Public tests complete; independent results pending.'}
        if should_repair and used<len(steps):
            name,args=steps[used]
            message={'role':'assistant','content':None,'tool_calls':[{'id':'pair-'+str(used),
                     'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
    reply={'model':body['model'],'choices':[{'message':message,
           'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}]}
    raw=json.dumps(reply).encode()
    handler.send_response(200);handler.send_header('Content-Type','application/json')
    handler.send_header('Content-Length',str(len(raw)));handler.end_headers();handler.wfile.write(raw)


class PairedWorkflowTests(unittest.TestCase):
    setUp=fixture.ChallengeWorkflowTests.setUp
    tearDown=fixture.ChallengeWorkflowTests.tearDown

    def test_net_gain_with_lost_passes_completes_review_but_cannot_release(self):
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(fixture.ROLES)]}
        # Same bounded graph as V1/V3: <=22 rollouts,133 requests,66 trusted
        # workflow batches,4450s+30s collection; one extra approval replay <=110s.
        with patch.object(fixture.Model,'do_POST',net_gain_model):
            run=self.service.start(registry,'paired-proof','gepa-evolution',{
                'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,
                'taskCallBudget':6,'callTimeoutSeconds':10,'maxSeconds':4450,
                'providerRevision':1,'expectedRevision':1})
            self.assertEqual(run['gepaConfig']['comparisonPolicy'],POLICY)
            self.assertEqual(run['gepaConfig']['provenance']['comparisonPolicy'],POLICY)
            self.assertTrue(self.service.completion_event.wait(4480),'No persisted terminal result')
        done=self.service.get_run(run['id'])
        self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult']
        self.assertFalse(result['eligible'])
        self.assertEqual(result['releaseBlockers'],['validation-task-regressed','heldout-task-regressed'])
        for split in ('validation','heldout'):
            self.assertEqual(result['final']['baseline'][split],{'passed':1,'total':3})
            self.assertEqual(result['final']['selected'][split],{'passed':2,'total':3})
            self.assertEqual(result['comparison']['splits'][split],
                             {'improved':2,'regressed':1,'retained-pass':0,'retained-fail':0})
        self.assertEqual(result['rollouts'],22)
        batches=self.service.logs.list(run_id=run['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(batches['matched'],66)
        calls=len(fixture.Model.calls)
        parser="""import fs from 'node:fs';import {validateGepaRun} from './dist/js/runtime-client.js';
import {gepaView} from './dist/js/gepa-view.js';
const run=validateGepaRun(JSON.parse(fs.readFileSync(0,'utf8')));
const html=gepaView({enabled:true,data:{gepa:{latestRun:run,activeVersionId:'GSV-baseline',versions:[],sdk:{available:true},optimizer:{available:true}}}});
if(!html.includes('逐題退步・未通過演化門檻')||!html.includes('CH-balanced-brackets')||!/<button[^>]*data-gepa-approve[^>]*disabled/.test(html))process.exit(1);
run.gepaResult.eligible=true;
try{validateGepaRun(run);process.exit(2);}catch(e){if(!e.message.includes('核准門檻'))throw e;}
"""
        parsed=subprocess.run(['node','--input-type=module','-e',parser],cwd=fixture.ROOT,
                              input=json.dumps(done),text=True,capture_output=True,timeout=10)
        self.assertEqual(parsed.returncode,0,parsed.stdout+parsed.stderr)
        with self.assertRaises(RuntimeError):
            self.service.gepa.approve(run['id'],1)
        # A forged saved eligibility flag cannot bypass independent approval replay.
        forged=copy.deepcopy(done);forged['gepaResult']['eligible']=True
        with patch.object(self.service,'get_run',return_value=forged), self.assertRaises(ValueError):
            self.service.gepa.approve(run['id'],1)
        self.assertEqual(self.service.gepa.snapshot()['activeVersionId'],'GSV-baseline')
        after=self.service.logs.list(run_id=run['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(after['matched'],88)
        directory=self.service.local/'runs'/run['id']
        cfg_path=directory/'gepa-config.json';original=cfg_path.read_bytes()
        cfg=json.loads(original);cfg.pop('comparisonPolicy');cfg_path.write_text(json.dumps(cfg))
        try:
            with self.assertRaisesRegex(ValueError,'comparison policy'):
                fixture.verify(directory)
        finally:
            cfg_path.write_bytes(original)
        self.assertEqual(len(fixture.Model.calls),calls)
        self.assertLessEqual(calls,133)
        self.assertFalse(self.service.ollama.operation.locked())
        print('PAIRED_WORKLOAD_RESULT',json.dumps({'rollouts':22,'requests':calls,
              'threePassBatches':66,'approvalBatches':88,'eligible':False}),flush=True)


if __name__=='__main__':
    unittest.main()
