"""Pinned SDK and GUI canonical three-pass final comparison, with no Docker claim."""
import json
import shutil
import subprocess
import unittest
import uuid

import challenge_workflow_test as fixture
from gepa_engine import verify
from gepa_validation_budget import repeated_fixture_budget
from runtime_service import RuntimeService, ROOT


class RepeatedFinalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.ChallengeWorkflowTests('test_real_optimizer_repair_review_frozen_bank_edit_and_approval')
        self.fixture.setUp()
        self.fixture.service.close()
        self.fixture.service=RuntimeService(self.fixture.temp.name,canonical=True)
        self.service=self.fixture.service

    def tearDown(self):
        outcome=getattr(getattr(self,'_outcome',None),'result',None)
        if outcome and any(case is self for case,_ in outcome.failures+outcome.errors):
            support=ROOT/'.local/test-reports/gepa-repeated'/uuid.uuid4().hex
            support.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(self.fixture.temp.name,support)
            print('M_REPEATED_SUPPORT',support,flush=True)
        self.fixture.tearDown()

    def test_three_fresh_final_passes_reviewer_canonical_records_and_approval(self):
        budget=repeated_fixture_budget(0)
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True}
                            for i,role in enumerate(fixture.ROLES)]}
        options={'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,
                 'taskCallBudget':4,'callTimeoutSeconds':10,'finalRepetitions':3,
                 'maxSeconds':budget['workflowSeconds'],'providerRevision':1,'expectedRevision':1}
        run=self.service.start(registry,'canonical-three-pass','gepa-evolution',options)
        self.assertTrue(self.service.completion_event.wait(budget['workflowSeconds']+30),'No terminal GEPA result')
        done=self.service.get_run(run['id'])
        self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult'];comparison=result['comparison']
        self.assertEqual(result['selectedSkill']['body'],fixture.IMPROVED)
        self.assertEqual((result['rollouts'],result['final']['selected']['heldout']),
                         (34,{'passed':9,'total':9}))
        self.assertEqual((comparison['repetitions'],len(comparison['tasks'])),(3,12))
        self.assertEqual(len(comparison['uncertainty']['taskWilson95']['selected']),2)
        directory=self.service.local/'runs'/run['id']
        self.assertEqual(verify(directory),result)
        with self.service.canonical.store.db() as db:
            evaluations=[json.loads(r[0]) for r in db.execute('SELECT data FROM evaluations ORDER BY rowid')]
        self.assertEqual(len(evaluations),34)
        for task_id in {r['taskId'] for r in comparison['tasks'] if r['split']=='heldout'}:
            for label in ('baseline','candidate'):
                self.assertEqual({e['repetition'] for e in evaluations if e['task_id']==task_id and e['label']==label},
                                 {0,1,2})
        parser="""import fs from 'node:fs';import {validateGepaRun} from './dist/js/runtime-client.js';
import {gepaResultsView} from './dist/js/gepa-results-view.js';
const run=JSON.parse(fs.readFileSync(0,'utf8'));validateGepaRun(run);
const html=gepaResultsView({selectedGepaRun:run,data:{gepa:{versions:[],activeVersionId:'GSV-baseline'}}});
if(!html.includes('第 3 次')||!html.includes('Wilson'))process.exit(1);
"""
        parsed=subprocess.run(['node','--input-type=module','-e',parser],cwd=ROOT,input=json.dumps(done),
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(parsed.returncode,0,parsed.stdout+parsed.stderr)
        requests=len(fixture.Model.calls)
        self.assertEqual(self.service.gepa.approve(run['id'],1)['revision'],2)
        self.assertEqual(len(fixture.Model.calls),requests)
        print('M_REPEATED_GEPA_RESULT',json.dumps({'rollouts':34,'evaluations':34,
              'requests':requests,'verificationBatches':102,'approvalBatches':34,
              'repetitions':3}),flush=True)


if __name__=='__main__':
    unittest.main()
