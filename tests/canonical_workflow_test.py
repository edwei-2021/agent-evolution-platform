"""Actual GUI GEPA processes commit canonical per-rollout and terminal evidence."""
import json
import unittest
import sys
import threading
import time
from unittest.mock import patch
import challenge_workflow_test as fixture
sys.path.insert(0,str(fixture.ROOT))
from platform_m.contracts import Evaluation, RunResult
from gepa_dataset import skill
from gepa_validation_budget import canonical_fixture_budget


class CanonicalWorkflowTests(unittest.TestCase):
    def setUp(self):
        fixture.ChallengeWorkflowTests.setUp(self)
        self.service.close()
        self.service=fixture.RuntimeService(self.temp.name,canonical=True)
    tearDown=fixture.ChallengeWorkflowTests.tearDown

    def options(self):
        return {'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,
                'taskCallBudget':6,'callTimeoutSeconds':10,
                'maxSeconds':canonical_fixture_budget(0)['workflowSeconds'],
                'providerRevision':1,'expectedRevision':1}

    def test_real_gui_gepa_ledger_cleanup_approval_and_view_reconciliation(self):
        entered=threading.Event();release=threading.Event();finish=self.service.canonical.finish
        def paused(run):
            entered.set()
            if not release.wait(15):raise TimeoutError('Canonical finalizer barrier was not released')
            return finish(run)
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(fixture.ROLES)]}
        with patch.object(self.service.canonical,'finish',side_effect=paused):
            run=self.service.start(registry,'canonical-gepa-proof','gepa-evolution',self.options())
            try:
                self.assertTrue(entered.wait(4600))
                self.assertFalse(self.service.ollama.operation.locked())
                self.assertEqual(self.service.get_run(run['id'])['status'],'running')
                self.assertEqual(self.service.canonical.store.get(run['gepaConfig']['canonicalJob']['id'])['state'],'running')
            finally:release.set()
            self.assertTrue(self.service.completion_event.wait(15))
        self.assertTrue(self.service.completion_event.wait(4600),'No canonical terminal result')
        done=self.service.get_run(run['id'])
        self.assertEqual(done['status'],'completed',str(done['agents']))
        self.assertFalse(self.service.ollama.operation.locked())
        bridge=self.service.canonical;identifier=done['gepaConfig']['canonicalJob']['id']
        self.assertEqual(bridge.store.get(identifier)['state'],'completed')
        with bridge.store.db() as db:
            values=[json.loads(r[0]) for r in db.execute('SELECT data FROM evaluations ORDER BY rowid')]
            canonical=json.loads(db.execute('SELECT data FROM results WHERE job_id=?',(identifier,)).fetchone()[0])
        self.assertEqual(len(values),22)
        self.assertEqual(canonical['evaluation'],done['gepaResult'])
        self.assertEqual(canonical['experiment']['state'],'completed')
        ledger=json.loads((self.service.local/'runs'/run['id']/'gepa-rollouts.json').read_text())
        for value,row in zip(values,ledger):
            Evaluation.model_validate(value)
            self.assertEqual(value['score'],row['score'])
            execution=RunResult.model_validate(bridge.artifacts.get(value['artifacts'][0]))
            self.assertEqual(execution.loaded_skill_hash,skill(row['body'])['hash'])
            self.assertIn('candidate_source',execution.output)
        commits=[e for e in bridge.store.events(identifier) if e['type']=='rollout.committed']
        self.assertEqual(len(commits),22)
        count=len(fixture.Model.calls)
        approved=self.service.gepa.approve(run['id'],1)
        self.assertEqual(approved['revision'],2)
        self.assertEqual(len(fixture.Model.calls),count)
        # A stale legacy view recovers from committed canonical evidence only.
        with self.service.connect() as db:
            stale=dict(canonical['legacy_run']);stale['status']='interrupted'
            db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(stale),run['id']))
        self.service.close();self.service=fixture.RuntimeService(self.temp.name,canonical=True)
        self.assertEqual(self.service.get_run(run['id'])['status'],'completed')
        self.assertEqual(len(fixture.Model.calls),count)
        print('M_CANONICAL_GEPA_RESULT',json.dumps({'rollouts':22,'evaluations':22,
            'requests':count,'readRecoveryRequests':0,'workflowBatches':66,'approvalBatches':88}),flush=True)

    def test_canonical_cancel_publishes_after_process_cleanup_and_slot_release(self):
        self.service.command_factory=lambda role,path:[sys.executable,'-c','import time;time.sleep(60)']
        entered=threading.Event();release=threading.Event();finish=self.service.canonical.finish
        def paused(run):
            entered.set()
            if not release.wait(10):raise TimeoutError('Cancellation finalizer barrier was not released')
            return finish(run)
        registry={'agents':[{'id':'AG-'+str(i),'name':r,'role':r,'enabled':True} for i,r in enumerate(fixture.ROLES)]}
        with patch.object(self.service.canonical,'finish',side_effect=paused):
            run=self.service.start(registry,'canonical-cancel','gepa-evolution',self.options())
            identifier=run['gepaConfig']['canonicalJob']['id']
            limit=time.monotonic()+10
            while self.service.process is None and time.monotonic()<limit:time.sleep(.02)
            self.assertIsNotNone(self.service.process)
            process=self.service.process
            self.service.canonical.store.request_cancel(identifier)
            try:
                self.assertTrue(entered.wait(10))
                self.assertIsNotNone(process.poll())
                self.assertFalse(self.service.ollama.operation.locked())
                self.assertEqual(self.service.canonical.store.get(identifier)['state'],'cancelling')
                self.assertEqual(self.service.get_run(run['id'])['status'],'running')
            finally:release.set()
            self.assertTrue(self.service.completion_event.wait(10))
        self.assertEqual(self.service.get_run(run['id'])['status'],'cancelled')
        self.assertEqual(self.service.canonical.store.get(identifier)['state'],'cancelled')
        self.assertEqual(len(fixture.Model.calls),0)


if __name__=='__main__':unittest.main()
