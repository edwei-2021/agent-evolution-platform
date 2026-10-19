"""V2 independent cases, persistence migration and explicit preset boundary."""
import copy
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from challenge_bank_test import Service, ROOT
from challenge_bank import ChallengeBank, validate_question, validate_snapshot, fixture
from serve_gui import GuiHandler, DIST
from repair_engine import trusted_test_batch

SEEDS=json.loads((ROOT/'data/python-challenges-v2.json').read_text())


class ChallengeV2Tests(unittest.TestCase):
    def test_failed_preset_validation_cannot_partially_disable_or_insert_questions(self):
        with tempfile.TemporaryDirectory() as root:
            bank=Service(root).challenges;before=bank.snapshot()
            with patch('challenge_bank.validate_question',side_effect=[None,None,None,ValueError('Bad reference')]):
                with self.assertRaisesRegex(ValueError,'Bad reference'):bank.install_v2(1)
            self.assertEqual(bank.snapshot(),before)

    def test_v2_oracles_also_pass_in_the_copied_isolated_evaluator(self):
        with tempfile.TemporaryDirectory() as root:
            from pathlib import Path
            target=Path(root)
            for name in ('repair_fixture.py','challenge_policy.py','repair_evaluator.py'):
                shutil.copyfile(ROOT/'scripts'/name,target/name)
            jobs=[{'source':q['reference'],'fixture':fixture(q),'split':split}
                  for q in SEEDS for split in ('visible','hidden')]
            run=subprocess.run([sys.executable,'-I','-S',str(target/'repair_evaluator.py')],
                input=json.dumps({'jobs':jobs}),capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            results=json.loads(run.stdout)['results']
            self.assertEqual(len(results),24)
            self.assertTrue(all(r['passed']==r['total'] for r in results))

    def test_all_twelve_references_and_faulty_starts_with_independent_edge_cases(self):
        self.assertEqual(len(SEEDS),12)
        self.assertEqual(len({q['group'] for q in SEEDS}),12)
        self.assertEqual(len({q['topic'] for q in SEEDS}),12)
        for question in SEEDS:
            with self.subTest(question=question['id']):
                validate_question(question,execute=True)
                self.assertGreaterEqual(len(question['hidden']),4)
                # Each shipped defect is witnessed in retained cases as well.
                result=trusted_test_batch([{'source':question['baseline'],'fixture':fixture(question),'split':'hidden'}])[0]
                self.assertLess(result['passed'],result['total'])

    def test_preset_preserves_custom_edits_and_old_frozen_runs_without_reseeding(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root);bank=service.challenges
            question=copy.deepcopy(bank.snapshot()['questions'][0]);question['title']='Saved custom title'
            bank.mutate(1,question,question['id'])
            before=bank.snapshot();frozen=bank.freeze(2)
            after=bank.install_v2(2)
            self.assertEqual((after['version'],after['revision']),('python-challenges-v2',3))
            self.assertEqual(len(after['questions']),24)
            self.assertEqual(after['questions'][:12],[dict(q,enabled=False) for q in before['questions']])
            self.assertEqual(bank.summary()['counts'],{'train':6,'validation':3,'heldout':3})
            self.assertEqual(validate_snapshot(frozen),frozen['data'])
            self.assertEqual(frozen['version'],'python-challenges-v1')
            new=bank.freeze(3);self.assertEqual(new['version'],'python-challenges-v2')
            self.assertNotIn('reference',json.dumps(new))
            self.assertTrue(all(t['id'].startswith('CH-v2-') for rows in new['data'].values() for t in rows))
            self.assertEqual(ChallengeBank(service).snapshot(),after)
            with patch('challenge_bank.validate_question',side_effect=AssertionError('No revalidation on conflict')):
                with self.assertRaises(RuntimeError):bank.install_v2(2)
                with self.assertRaises(RuntimeError):bank.install_v2(3)
            changed=copy.deepcopy(new);changed['version']='unknown'
            with self.assertRaises(ValueError):validate_snapshot(changed)

    def test_old_sqlite_schema_migrates_without_changing_revision_or_questions(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root);saved=service.challenges.snapshot()
            with service.connect() as db:
                db.execute('DROP TABLE challenge_bank')
                db.execute('CREATE TABLE challenge_bank (singleton INTEGER PRIMARY KEY, revision INTEGER, data TEXT)')
                db.execute('INSERT INTO challenge_bank VALUES (1,7,?)',(json.dumps(saved['questions']),))
            migrated=ChallengeBank(service).snapshot()
            self.assertEqual(migrated['version'],'python-challenges-v1')
            self.assertEqual(migrated['revision'],7);self.assertEqual(migrated['questions'],saved['questions'])

    def test_preset_http_requires_token_revision_and_explicit_post_without_model_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root)
            class Quiet(GuiHandler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)))
            server.runtime=service;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,body=None,auth=True):
                conn=HTTPConnection('127.0.0.1',server.server_port,timeout=70)
                headers={'Content-Type':'application/json'}
                if auth:headers['X-Lab-Token']=service.csrf_token
                conn.request(method,'/api/v1/challenges/presets/repair-v2',json.dumps(body) if body else None,headers)
                response=conn.getresponse();data=json.loads(response.read());conn.close();return response.status,data
            try:
                self.assertEqual(request('GET')[0],404)
                self.assertEqual(request('POST',{'expectedRevision':1},False)[0],403)
                self.assertEqual(request('POST',{'expectedRevision':0})[0],409)
                self.assertEqual(request('POST',{'expectedRevision':1,'extra':True})[0],400)
                status,data=request('POST',{'expectedRevision':1});self.assertEqual(status,200)
                self.assertEqual(data['version'],'python-challenges-v2')
                self.assertEqual(request('POST',{'expectedRevision':2})[0],409)
                self.assertEqual(service.challenges.snapshot()['revision'],2)
            finally:server.shutdown();server.server_close();thread.join()
