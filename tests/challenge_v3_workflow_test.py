"""Exact V3 balanced-batch workflow with real pinned SDKs and scripted HTTP replies."""
import json
import subprocess
import unittest
from unittest.mock import patch
import challenge_workflow_test as fixture
from challenge_v3_test import SEEDS


class ChallengeV3WorkflowTests(unittest.TestCase):
    setUp=fixture.ChallengeWorkflowTests.setUp
    tearDown=fixture.ChallengeWorkflowTests.tearDown

    def test_v3_frozen_dataset_all_three_verifiers_frontend_and_approval(self):
        self.service.challenges.install_v3(1,0)
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(fixture.ROLES)]}
        # 22 rollouts, 133 request slots at 10s, <=24 test tools/task,
        # three independent 5s batches/task + 120s startup + 30s cleanup.
        # Workflow=4450; terminal collection=4480; approval extra <=110s.
        with patch.dict(fixture.BY_ID,{q['id']:q for q in SEEDS}):
            run=self.service.start(registry,'v3-proof','gepa-evolution',{
                'profile':'bank','bankRevision':2,'metricBudget':10,'proposalBudget':1,
                'taskCallBudget':6,'callTimeoutSeconds':10,'maxSeconds':4450,
                'providerRevision':1,'expectedRevision':1})
            frozen=run['gepaConfig']['datasetSnapshot']
            self.assertEqual(frozen['version'],'python-challenges-v3')
            q=dict(SEEDS[0]);q['title']='Edited after freezing V3'
            self.service.challenges.mutate(2,q,q['id'])
            self.assertTrue(self.service.completion_event.wait(4480),'No persisted terminal result')
        done=self.service.get_run(run['id'])
        self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult'];self.assertTrue(result['eligible'])
        self.assertEqual(result['releaseBlockers'],[])
        self.assertEqual(len(result['comparison']['tasks']),6)
        for split in ('validation','heldout'):
            self.assertEqual(result['comparison']['splits'][split],
                             {'improved':3,'regressed':0,'retained-pass':0,'retained-fail':0})
        self.assertEqual(result['final']['selected']['validation'],{'passed':3,'total':3})
        self.assertEqual(result['final']['selected']['heldout'],{'passed':3,'total':3})
        self.assertEqual(done['gepaConfig']['datasetSnapshot'],frozen)
        self.assertLessEqual(result['rollouts'],22);self.assertLessEqual(result['calls'],133)
        batches=self.service.logs.list(run_id=run['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(batches['matched'],3*result['rollouts'])
        directory=self.service.local/'runs'/run['id']
        for child in (directory/'rollouts').iterdir():
            cfg=json.loads((child/'repair-config.json').read_text())
            calls=json.loads((child/'repair-calls.json').read_text())
            self.assertNotIn('reference',cfg['fixture'])
            self.assertNotIn(next(q['reference'] for q in SEEDS if q['id']==cfg['taskId']),str(calls[0]['request']))
        parser="""import fs from 'node:fs';import {validateGepaRun} from './dist/js/runtime-client.js';
validateGepaRun(JSON.parse(fs.readFileSync(0,'utf8')));"""
        parsed=subprocess.run(['node','--input-type=module','-e',parser],cwd=fixture.ROOT,input=json.dumps(done),text=True,capture_output=True,timeout=10)
        self.assertEqual(parsed.returncode,0,parsed.stdout+parsed.stderr)
        archive=fixture.skill_snapshot(self.service.root,run['id'])
        self.assertEqual(archive['conditions']['datasetVersion'],'python-challenges-v3')
        self.assertEqual(archive['outcome']['eligible'],True)
        approved=self.service.gepa.approve(run['id'],1)
        self.assertEqual(approved['revision'],2)
        after=self.service.logs.list(run_id=run['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(after['matched'],4*result['rollouts'])
        print('V3_WORKLOAD_RESULT',json.dumps({'rollouts':result['rollouts'],'requests':result['calls'],
              'threePassBatches':batches['matched'],'approvalBatches':after['matched']}),flush=True)
