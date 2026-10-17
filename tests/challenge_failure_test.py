"""Exact task-cap failures and unexecuted final tail, with real pinned SDKs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import challenge_workflow_test as workflow
from gepa_engine import verify
from repair_engine import TASK_FAILURE_POLICY, task_call_limit, verify as verify_repair
from skill_engine import write


class ChallengeFailureTests(unittest.TestCase):
    setUp=workflow.ChallengeWorkflowTests.setUp
    tearDown=workflow.ChallengeWorkflowTests.tearDown

    def options(self,calls=6):
        # Same bounded 22-rollout graph as the normal integration: model calls,
        # 24 possible visible tools and all three five-second verifications.
        rollouts=22;requests=rollouts*calls+1
        seconds=120+requests*10+rollouts*(24*5+3*5)+30
        return {'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,'taskCallBudget':calls,
                'callTimeoutSeconds':10,'maxSeconds':seconds,'providerRevision':1,'expectedRevision':1}

    def start(self):
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(workflow.ROLES)]}
        options=self.options();run=self.service.start(registry,'bounded-cap-proof','gepa-evolution',options)
        self.assertTrue(self.service.completion_event.wait(options['maxSeconds']+30),'Terminal persistence missing')
        return self.service.get_run(run['id'])

    def test_failed_search_and_final_tasks_score_zero_and_remaining_tail_is_reviewed(self):
        workflow.Model.mode='bounded-caps';done=self.start()
        self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult'];self.assertTrue(result['eligible'])
        self.assertEqual(result['final']['selected']['validation'],{'passed':2,'total':3})
        self.assertEqual(result['final']['selected']['heldout'],{'passed':2,'total':3})
        failures=result['taskFailures'];self.assertEqual({f['stage'] for f in failures},{'search','baseline','selected'})
        self.assertTrue(any(f['taskId']=='CH-stable-record-sort' for f in failures))
        directory=self.service.local/'runs'/done['id'];ledger=json.loads((directory/'gepa-rollouts.json').read_text())
        batches=self.service.logs.list(run_id=done['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(batches['matched'],3*len(ledger))
        self.assertEqual(done['gepaProgress']['verification']['verifiedRollouts'],len(ledger))
        print('TASK_CAP_WORKLOAD_RESULT',json.dumps({'rollouts':len(ledger),'verificationBatches':batches['matched'],'failedTasks':len(failures),'modelRequests':result['calls']}),flush=True)
        for row in ledger:
            child=directory/'rollouts'/row['id'];evaluated=json.loads((child/'repair-evaluation.json').read_text())
            if row['taskOutcome']=='call-limit':
                self.assertEqual(row['score'],0);self.assertFalse(evaluated['repairPassed']);self.assertEqual(row['sdkStopReason'],'max_iterations')
                self.assertEqual(evaluated['calls'],6)
        proposals=json.loads((directory/'gepa-proposals.json').read_text())
        self.assertTrue(any(t.get('taskOutcome')=='call-limit' for p in proposals for t in p['training']))
        self.assertEqual(verify(directory),result);self.assertFalse(self.service.ollama.operation.locked())
        parser="""import fs from 'node:fs';import {validateGepaRun} from './dist/js/runtime-client.js';import {gepaResultsView} from './dist/js/gepa-results-view.js';
const run=JSON.parse(fs.readFileSync(0,'utf8'));validateGepaRun(run);
const html=gepaResultsView({data:{gepa:{latestRun:run,versions:[]}}});if(!html.includes('均計 0 分'))throw Error('Missing failed-task result');
run.gepaResult.taskFailures[0].reason='completed';try{validateGepaRun(run);process.exit(1);}catch(e){if(!e.message.includes('單題失敗'))throw e;}
"""
        p=subprocess.run(['node','--input-type=module','-e',parser],cwd=workflow.ROOT,input=json.dumps(done),text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.service.gepa.approve(done['id'],1)
        failed=next(r for r in ledger if r['taskOutcome']=='call-limit');path=directory/'rollouts'/failed['id']/'repair-sdk-result.json'
        report=json.loads(path.read_text());report['stopReason']='completed';write(path,report)
        with self.assertRaises(ValueError):verify(directory)

    def test_http_failure_aborts_without_scoring_zero_or_running_final_tasks(self):
        workflow.Model.mode='http-failure';done=self.start()
        self.assertEqual(done['status'],'failed');self.assertIsNone(done.get('gepaResult'))
        directory=self.service.local/'runs'/done['id'];ledger=json.loads((directory/'gepa-rollouts.json').read_text())
        self.assertTrue(all(row['stage']=='search' for row in ledger))
        calls=json.loads((directory/'gepa-calls.json').read_text());self.assertEqual(sum(c['status']=='failed' for c in calls),1)
        self.assertEqual(sum('Task ID: CH-signed-decimal' in str(c['messages']) for c in workflow.Model.calls),1)
        self.assertFalse(self.service.ollama.operation.locked())

    def test_last_call_correct_source_is_still_a_failed_task_without_sdk_completion(self):
        workflow.Model.mode='last-write'
        cfg=self.service.gepa.freeze(self.options(calls=2));cfg['runId']='RUN-cap-fixture'
        directory=self.service.local/'runs'/cfg['runId'];directory.mkdir(parents=True)
        for name in ('gepa-rollouts.json','gepa-calls.json','gepa-proposals.json'):write(directory/name,[])
        from gepa_sdk import Session
        row,_=Session(directory,cfg).rollout(cfg['datasetSnapshot']['data']['validation'][0],cfg['baseline']['skill']['body'],'baseline')
        child=directory/'rollouts'/row['id'];child_cfg=json.loads((child/'repair-config.json').read_text())
        result=verify_repair(child,child_cfg)
        self.assertTrue(all(m['passed']==m['total'] for m in result['candidate'].values()))
        self.assertFalse(result['repairPassed']);self.assertEqual(result['taskOutcome'],'call-limit');self.assertEqual(row['score'],0)


class CapClassificationTests(unittest.TestCase):
    def test_late_rollout_publication_cannot_erase_later_calls(self):
        from gepa_sdk import Session,GlobalRunner
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'run';directory.mkdir()
            for name in ('gepa-calls.json','gepa-rollouts.json','gepa-proposals.json'):write(directory/name,[])
            cfg={'logRoot':root};session=Session(directory,cfg)
            first_dir=directory/'rollouts/R0001';first_dir.mkdir(parents=True)
            first=GlobalRunner(first_dir,cfg,session,{'rolloutId':'R0001'})
            first.calls=[{'id':1,'status':'completed'}];first.publish()
            second_dir=directory/'rollouts/R0002';second_dir.mkdir()
            second=GlobalRunner(second_dir,cfg,session,{'rolloutId':'R0002'})
            second.calls=[{'id':1,'status':'completed'}];second.publish()
            before=(directory/'gepa-calls.json').read_bytes()
            first.publish(toolCalls=1)
            self.assertEqual((directory/'gepa-calls.json').read_bytes(),before)
            self.assertEqual(len(session.calls),2)
            self.assertEqual(json.loads((directory/'gepa-progress.json').read_text())['lastCall']['rolloutId'],'R0002')

    def test_only_a_complete_local_call_cap_qualifies_and_infrastructure_remains_fatal(self):
        cfg={'taskFailurePolicy':TASK_FAILURE_POLICY,'fixture':{'policy':'python-challenge-v1'},'callBudget':2,'deadlineEpoch':time.time()+10}
        call={'status':'completed','finalSummary':False,'finishedAt':time.time(),'response':{'choices':[{'message':{'tool_calls':[{}]}}]}}
        calls=[copy.deepcopy(call),copy.deepcopy(call)];sdk={'stopReason':'max_iterations','error':None}
        self.assertTrue(task_call_limit(cfg,calls,sdk,[]))
        variants=[({**cfg,'taskFailurePolicy':'other'},calls,sdk,[]),(cfg,calls[:1],sdk,[]),
                  (cfg,[{**call,'status':'failed'},call],sdk,[]),(cfg,calls,{**sdk,'error':'HTTP failed'},[]),
                  (cfg,calls,{**sdk,'stopReason':'cancelled'},[]),(cfg,calls,sdk,[{'name':'run_tests','status':'failed'}]),
                  (cfg,[call,{**call,'finalSummary':True}],sdk,[]),(cfg,[call,{**call,'finishedAt':cfg['deadlineEpoch']+1}],sdk,[])]
        for args in variants:
            with self.subTest(variant=args):self.assertFalse(task_call_limit(*args))


if __name__=='__main__':unittest.main()
