"""Sixty-task catalog, independent oracles and immutable balanced batches."""
import copy
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import itertools
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from challenge_bank_test import Service, ROOT
from challenge_bank import catalog_v3, catalog_batch, fixture, validate_question, validate_snapshot
from repair_engine import trusted_test_batch
from serve_gui import GuiHandler, DIST

SEEDS=catalog_v3()
BY_ID={q['id']:q for q in SEEDS}


class ChallengeV3Tests(unittest.TestCase):
    def test_all_sixty_references_in_copied_isolated_evaluator(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)
            for name in ('repair_fixture.py','challenge_policy.py','repair_evaluator.py'):
                shutil.copyfile(ROOT/'scripts'/name,target/name)
            for start in range(0,60,10):
                jobs=[{'source':q['reference'],'fixture':fixture(q),'split':split}
                      for q in SEEDS[start:start+10] for split in ('visible','hidden')]
                run=subprocess.run([sys.executable,'-I','-S',str(target/'repair_evaluator.py')],
                    input=json.dumps({'jobs':jobs}),capture_output=True,text=True,timeout=5)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                results=json.loads(run.stdout)['results']
                self.assertEqual(len(results),20)
                self.assertTrue(all(r['passed']==r['total'] for r in results))

    def test_sixty_distinct_programs_all_oracles_and_retained_fault_witnesses(self):
        self.assertEqual(len(SEEDS),60)
        self.assertEqual(len({q['baseline'] for q in SEEDS}),60)
        self.assertEqual(len({q['reference'] for q in SEEDS}),60)
        for level in ('easy','medium','hard'):
            self.assertEqual(sum(q['difficulty']==level for q in SEEDS),20)
        for q in SEEDS:
            with self.subTest(id=q['id']):
                validate_question(q,execute=True)
                self.assertGreaterEqual(len(q['hidden']),4)
                result=trusted_test_batch([{'source':q['baseline'],'fixture':fixture(q),'split':'hidden'}])[0]
                self.assertLess(result['passed'],result['total'])

    def test_five_disjoint_batches_cover_catalog_without_group_split_leakage(self):
        seen=set();groups={}
        for index in range(5):
            ids=catalog_batch(SEEDS,index)
            self.assertEqual(len(ids),12);self.assertFalse(ids & seen);seen.update(ids)
            for level in ('easy','medium','hard'):
                for split,n in [('train',2),('validation',1),('heldout',1)]:
                    self.assertEqual(sum(q['id'] in ids and q['difficulty']==level and q['split']==split for q in SEEDS),n)
        for q in SEEDS:
            self.assertEqual(groups.setdefault(q['group'],q['split']),q['split'])
        self.assertEqual(seen,set(BY_ID))
        for index in (-1,5,True,1.0,None):
            with self.assertRaises(ValueError):catalog_batch(SEEDS,index)

    def test_import_and_batch_changes_preserve_edits_v1_v2_and_frozen_runs(self):
        with tempfile.TemporaryDirectory() as root:
            bank=Service(root).challenges
            v1=bank.freeze(1);bank.install_v2(1)
            q=copy.deepcopy(bank.snapshot()['questions'][12]);q['title']='Operator custom edit'
            bank.mutate(2,q,q['id']);before=bank.snapshot();v2=bank.freeze(3)
            snap=bank.install_v3(3,0)
            self.assertEqual((snap['version'],snap['revision'],len(snap['questions'])),('python-challenges-v3',4,72))
            self.assertEqual(next(x for x in snap['questions'] if x['id']==q['id'])['title'],q['title'])
            for old in before['questions']:
                saved=next(x for x in snap['questions'] if x['id']==old['id'])
                self.assertEqual({k:v for k,v in saved.items() if k!='enabled'},{k:v for k,v in old.items() if k!='enabled'})
            frozen=[]
            for index in range(5):
                if index:snap=bank.install_v3(snap['revision'],index)
                self.assertEqual(bank.summary()['counts'],{'train':6,'validation':3,'heldout':3})
                f=bank.freeze(snap['revision']);frozen.append(copy.deepcopy(f))
                ids={q['id'] for rows in f['data'].values() for q in rows}
                self.assertEqual(ids,catalog_batch(SEEDS,index))
                self.assertTrue(all('reference' not in q and 'reference' not in q['fixture']
                                    for rows in f['data'].values() for q in rows))
            self.assertEqual(len(bank.snapshot()['questions']),72)
            for f in [v1,v2,*frozen]:self.assertEqual(validate_snapshot(f),f['data'])
            with self.assertRaises(RuntimeError):bank.install_v3(3,0)

    def test_invalid_edited_splits_and_failed_validation_are_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            bank=Service(root).challenges;before=bank.snapshot()
            with patch('challenge_bank.validate_question',side_effect=ValueError('Bad reference')):
                with self.assertRaises(ValueError):bank.install_v3(1,0)
            self.assertEqual(bank.snapshot(),before)
            bank.install_v3(1,0)
            q=copy.deepcopy(next(q for q in bank.snapshot()['questions'] if q['id'] in catalog_batch(SEEDS,1)))
            q['split']='heldout' if q['split']=='train' else 'train'
            bank.mutate(2,q,q['id']);before=bank.snapshot()
            with self.assertRaisesRegex(ValueError,'was edited'):bank.install_v3(3,1)
            self.assertEqual(bank.snapshot(),before)

    def test_http_preset_auth_fields_revision_and_zero_model_work(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root)
            class Quiet(GuiHandler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)))
            server.runtime=service;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(body,auth=True):
                conn=HTTPConnection('127.0.0.1',server.server_port,timeout=360)
                headers={'Content-Type':'application/json'}
                if auth:headers['X-Lab-Token']=service.csrf_token
                conn.request('POST','/api/v1/challenges/presets/repair-v3',json.dumps(body),headers)
                response=conn.getresponse();data=json.loads(response.read());conn.close();return response.status,data
            try:
                self.assertEqual(post({'expectedRevision':1,'batch':0},False)[0],403)
                self.assertEqual(post({'expectedRevision':1,'batch':5})[0],400)
                self.assertEqual(post({'expectedRevision':1,'batch':0,'extra':True})[0],400)
                self.assertEqual(post({'expectedRevision':0,'batch':0})[0],409)
                status,snap=post({'expectedRevision':1,'batch':0});self.assertEqual(status,200)
                self.assertEqual(snap['version'],'python-challenges-v3')
                self.assertEqual(len(snap['questions']),72)
                self.assertEqual(post({'expectedRevision':1,'batch':1})[0],409)
                self.assertEqual(post({'expectedRevision':2,'batch':4})[0],200)
            finally:server.shutdown();server.server_close();thread.join()

    def test_harder_oracles_agree_with_independent_exhaustive_small_instances(self):
        rng=random.Random(20261020)
        cases={name:[] for name in ('knapsack','max-flow','optimal-wrap','huffman-cost','regex-match')}
        for repeat in range(16):
            items=[[rng.randint(1,4),rng.randint(0,6)] for _ in range(rng.randint(0,5))]
            cap=rng.randint(0,8);poss=[]
            for mask in itertools.product((0,1),repeat=len(items)):
                weight=sum(mask[i]*items[i][0] for i in range(len(items)))
                value=sum(mask[i]*items[i][1] for i in range(len(items)))
                if weight<=cap:poss.append((-value,weight))
            value,weight=min(poss)
            cases['knapsack'].append({'input':{'capacity':cap,'items':items},'expected':{'value':-value,'weight':weight}})
            n=rng.randint(2,4);edges=[[rng.randrange(n),rng.randrange(n),rng.randint(0,4)] for _ in range(8)]
            cuts=[]
            for mask in itertools.product((0,1),repeat=n-2):
                cut={0}|{i+1 for i,x in enumerate(mask) if x}
                cuts.append(sum(w for a,b,w in edges if a in cut and b not in cut))
            cases['max-flow'].append({'input':{'n':n,'source':0,'sink':n-1,'edges':edges},'expected':min(cuts)})
            words=['x'*rng.randint(1,3) for _ in range(rng.randint(1,5))];width=rng.randint(3,7);options=[]
            for mask in itertools.product((0,1),repeat=len(words)-1):
                breaks=[i+1 for i,x in enumerate(mask) if x]+[len(words)]
                starts=[0]+breaks[:-1];lines=[' '.join(words[a:b]) for a,b in zip(starts,breaks)]
                if all(len(line)<=width for line in lines):
                    options.append((sum((width-len(line))**2 for line in lines[:-1]),breaks,lines))
            cost,breaks,lines=min(options)
            cases['optimal-wrap'].append({'input':{'words':words,'width':width},'expected':{'cost':cost,'lines':lines}})
            weights=[rng.randint(0,5) for _ in range(rng.randint(0,5))]
            def all_merges(values):
                if len(values)<2:return 0
                return min(values[i]+values[j]+all_merges([v for k,v in enumerate(values) if k not in (i,j)]+[values[i]+values[j]])
                           for i in range(len(values)) for j in range(i+1,len(values)))
            cases['huffman-cost'].append({'input':weights,'expected':all_merges(weights)})
            pattern=''.join(rng.choice(('a','b','.'))+rng.choice(('','*')) for _ in range(rng.randint(0,4)))
            text=''.join(rng.choice('ab') for _ in range(rng.randint(0,5)))
            cases['regex-match'].append({'input':{'text':text,'pattern':pattern},'expected':re.fullmatch(pattern,text) is not None})
        for name,items in cases.items():
            with self.subTest(oracle=name):
                q=BY_ID['CH-v3-'+name];f=fixture(q);f['hidden']=items
                result=trusted_test_batch([{'source':q['reference'],'fixture':f,'split':'hidden'}])[0]
                self.assertEqual(result['passed'],result['total'],result)
