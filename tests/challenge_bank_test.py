"""Seed oracles, policy boundaries, revisioned CRUD and frozen split isolation."""
from contextlib import contextmanager
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from challenge_bank import ChallengeBank, fixture, validate_question, validate_snapshot
from challenge_policy import validate_source
from debug_log import DebugLog
from repair_engine import ROOT, trusted_test_batch
from gepa_store import GepaStore
from serve_gui import GuiHandler,DIST

SEEDS=json.loads((ROOT/'data/python-challenges-v1.json').read_text())

class Service:
    def __init__(self,root):
        self.root=Path(root);self.local=self.root/'.local';self.local.mkdir(exist_ok=True)
        self.lock=threading.RLock();self.csrf_token='challenge-fixture-local-token'
        self.logs=DebugLog(root);self.challenges=ChallengeBank(self)
    @contextmanager
    def connect(self):
        with sqlite3.connect(self.local/'bank.sqlite3') as db:yield db

class ChallengeBankTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=Service(self.temp.name);self.bank=self.service.challenges

    def test_twelve_distinct_oracles_pass_with_real_defects_and_three_difficulties(self):
        self.assertGreaterEqual(len(SEEDS),12)
        self.assertEqual({q['difficulty'] for q in SEEDS},{'easy','medium','hard'})
        self.assertEqual(len({q['baseline'] for q in SEEDS}),len(SEEDS))
        self.assertEqual(len({q['topic'] for q in SEEDS}),len(SEEDS))
        for question in SEEDS:
            with self.subTest(question=question['id']):validate_question(question,execute=True)
        self.assertEqual(self.bank.summary()['counts'],{'train':6,'validation':3,'heldout':3})

    def test_crud_persists_revisions_without_reseeding_and_keeps_old_dataset(self):
        frozen=self.bank.freeze(1);before=copy.deepcopy(frozen)
        question=copy.deepcopy(SEEDS[0]);question.pop('id');question['title']='User edited title'
        created=self.bank.mutate(1,question);self.assertEqual(created['revision'],2)
        new_id=created['questions'][-1]['id']
        question['prompt']+=' Preserve all non-whitespace characters.'
        edited=self.bank.mutate(2,question,new_id);self.assertEqual(edited['revision'],3)
        self.bank.mutate(3,identifier=new_id,delete=True)
        restored=ChallengeBank(self.service).snapshot()
        self.assertEqual(restored['revision'],4);self.assertEqual(len(restored['questions']),12)
        self.assertEqual(frozen,before);self.assertEqual(validate_snapshot(frozen),before['data'])
        self.assertNotEqual(self.bank.freeze(4)['hash'],frozen['hash'])

    def test_conflict_invalid_reference_and_already_correct_start_never_change_state(self):
        question=copy.deepcopy(SEEDS[0]);question['reference']='def solve(data):\n    return "wrong"\n'
        with self.assertRaisesRegex(ValueError,'Reference'):self.bank.mutate(1,question)
        self.assertEqual(self.bank.snapshot()['revision'],1)
        question=copy.deepcopy(SEEDS[0]);question['baseline']=question['reference']
        with self.assertRaisesRegex(ValueError,'already passes'):self.bank.mutate(1,question)
        with self.assertRaises(RuntimeError):self.bank.mutate(0,question)
        self.assertEqual(len(self.bank.snapshot()['questions']),12)

    def test_cross_split_groups_empty_selection_and_tampered_snapshot_fail_closed(self):
        frozen=self.bank.freeze(1)
        def keys(value):
            if isinstance(value,dict):
                self.assertNotIn('reference',value)
                for child in value.values():keys(child)
            elif isinstance(value,list):
                for child in value:keys(child)
        keys(frozen)
        question=copy.deepcopy(SEEDS[6]);question['group']=SEEDS[0]['group']
        self.bank.mutate(1,question,question['id'])
        with self.assertRaisesRegex(ValueError,'cross'):self.bank.freeze(2)
        self.assertFalse(self.bank.summary()['ready'])
        altered=copy.deepcopy(frozen);altered['data']['heldout'][0]['fixture']['hidden'][0]['expected']='tampered'
        with self.assertRaisesRegex(ValueError,'hash'):validate_snapshot(altered)
        with self.service.connect() as db:db.execute('UPDATE challenge_bank SET revision=3,data=?',(json.dumps([]),))
        self.assertFalse(self.bank.summary()['ready'])
        self.assertEqual(ChallengeBank(self.service).snapshot()['questions'],[])

    def test_unsafe_or_incompatible_syntax_is_rejected_including_neighboring_forms(self):
        for source in ['import os\ndef solve(data):\n return data',
                       'def solve(data):\n return data.__class__',
                       'def solve(data):\n return open("/etc/passwd")',
                       'def solve(data):\n return __import__("os")',
                       'def solve(data):\n return solve(data)',
                       'def solve(data):\n return "{0.__class__}".format(data)',
                       'def solve(data):\n global stolen\n return data',
                       'def solve(data):\n raise RuntimeError',
                       'def solve(data):\n raise ValueError from None',
                       'def solve(data=[]):\n return data',
                       'def clamp(value,lower,upper):\n return value']:
            with self.subTest(source=source),self.assertRaises((ValueError,SyntaxError)):validate_source(source)
        for source in ['def solve(data):\n raise ValueError', 'def solve(data):\n raise ValueError("invalid")']:
            validate_source(source)

    def test_input_mutation_nonjson_outputs_and_bool_integer_confusion_are_not_correct(self):
        f=fixture(SEEDS[1]);f['visible']=[{'input':[1,2],'expected':[2,1]}]
        rows=trusted_test_batch([{'source':'def solve(data):\n data.reverse()\n return data','split':'visible','fixture':f}])
        self.assertEqual(rows[0]['passed'],0);self.assertFalse(rows[0]['records'][0]['inputUnchanged'])
        f['visible']=[{'input':0,'raises':'ValueError'}]
        jobs=[{'source':s,'split':'visible','fixture':f} for s in ['def solve(data):\n return ValueError','def solve(data):\n return float("nan")']]
        self.assertEqual([r['passed'] for r in trusted_test_batch(jobs)],[0,0])
        f['visible']=[{'input':0,'expected':True}]
        self.assertEqual(trusted_test_batch([{'source':'def solve(data):\n return 1','split':'visible','fixture':f}])[0]['passed'],0)
        f['visible']=[{'input':[1.0],'expected':1.0}]
        tiny_mutation='def solve(data):\n data[0] += 0.0000000001\n return 1.0'
        row=trusted_test_batch([{'source':tiny_mutation,'split':'visible','fixture':f}])[0]
        self.assertEqual(row['passed'],0);self.assertFalse(row['records'][0]['inputUnchanged'])

    def test_reference_timeout_is_bounded_and_cannot_save_or_dispatch_a_model(self):
        question=copy.deepcopy(SEEDS[0]);question['reference']='def solve(data):\n    while True:\n        pass\n'
        with self.assertRaises(ValueError):self.bank.mutate(1,question)
        self.assertEqual(self.bank.snapshot()['revision'],1)

    def test_invalid_bank_submission_stops_before_sdk_probe_and_provider_dispatch(self):
        provider={'revision':1,'config':{'model':'fixture-local','maxTokens':256}}
        self.service.ollama=SimpleNamespace(lock=threading.RLock(),frozen=lambda:provider)
        store=object.__new__(GepaStore);store.service=self.service
        store.snapshot=Mock(side_effect=AssertionError('Cold SDK discovery must not start'))
        store.check_revision=Mock()
        options={'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,'taskCallBudget':10,
                 'maxSeconds':3600,'callTimeoutSeconds':60,'providerRevision':1,'expectedRevision':1}
        with self.assertRaisesRegex(ValueError,'max output tokens'):store.freeze(options)
        with self.assertRaisesRegex(RuntimeError,'changed'):store.freeze({**options,'bankRevision':0})
        with self.assertRaisesRegex(ValueError,'metricBudget'):store.freeze({**options,'metricBudget':9})
        store.snapshot.assert_not_called()

    def test_packaged_isolated_policy_matches_native_evaluation_and_legacy_remains_separate(self):
        target=Path(self.temp.name)/'image';target.mkdir()
        for name in ('repair_fixture.py','challenge_policy.py','repair_evaluator.py'):shutil.copyfile(ROOT/'scripts'/name,target/name)
        jobs=[{'source':q['reference'],'split':'hidden','fixture':fixture(q)} for q in SEEDS]
        completed=subprocess.run([sys.executable,'-I','-S',str(target/'repair_evaluator.py')],input=json.dumps({'jobs':jobs}),text=True,capture_output=True,timeout=5)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        result=json.loads(completed.stdout)['results'];self.assertTrue(all(r['passed']==r['total'] for r in result))
        from repair_fixture import validate_source as legacy
        with self.assertRaises(ValueError):legacy(SEEDS[1]['reference'])

    def test_http_crud_requires_origin_and_token_and_uses_optimistic_revision(self):
        class Quiet(GuiHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));server.runtime=self.service
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,body=None,headers=None):
            h={'Content-Type':'application/json',**(headers or {})}
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,h)
            response=conn.getresponse();data=json.loads(response.read());status=response.status;conn.close();return status,data
        try:
            self.assertEqual(request('/api/v1/challenges')[0],200)
            self.assertEqual(request('/api/v1/challenges',headers={'Origin':'https://outside.invalid'})[0],403)
            body={'expectedRevision':1,'challenge':copy.deepcopy(SEEDS[0])}
            self.assertEqual(request('/api/v1/challenges',body)[0],403)
            auth={'X-Lab-Token':self.service.csrf_token}
            malformed=copy.deepcopy(body);malformed['challenge']['baseline']='def solve(data)\n return data'
            status,error=request('/api/v1/challenges',malformed,auth)
            self.assertEqual(status,400);self.assertIn('syntax error',error['error'])
            self.assertEqual(self.bank.snapshot()['revision'],1)
            status,data=request('/api/v1/challenges',body,auth);self.assertEqual(status,201)
            id=data['questions'][-1]['id'];self.assertEqual(data['revision'],2)
            self.assertEqual(request('/api/v1/challenges',body,auth)[0],409)
            status,data=request(f'/api/v1/challenges/{id}/delete',{'expectedRevision':2},auth)
            self.assertEqual(status,200);self.assertEqual(data['revision'],3)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
