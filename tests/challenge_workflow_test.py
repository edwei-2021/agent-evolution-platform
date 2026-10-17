"""Exact real-SDK challenge search, frozen-bank edits, review and approval proof."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from challenge_bank import validate_snapshot
from gepa_engine import REFLECTION_SYSTEM,verify
from ollama_bridge import DEFAULTS
from runtime_service import RuntimeService,ROLES,ROOT

SEEDS=json.loads((ROOT/'data/python-challenges-v1.json').read_text())
BY_ID={q['id']:q for q in SEEDS}
IMPROVED='CHALLENGE_IMPROVED: Follow the task-specific function contract. Inspect failure categories, repair boundary conditions without mutating inputs, test again, then summarize.'

class Model(BaseHTTPRequestHandler):
    calls=[];mode='normal'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));type(self).calls.append(body)
        messages=body['messages'];message={'role':'assistant','content':'No repair attempted with this baseline.'}
        matched=re.search(r'Task ID: (CH-[A-Za-z0-9-]+)',str(messages));identifier=matched[1] if matched else None
        improved=IMPROVED in str(messages)
        if messages[0]['content']==REFLECTION_SYSTEM:
            message['content']=json.dumps({'skill_body':IMPROVED})
        elif type(self).mode=='http-failure' and identifier=='CH-signed-decimal':
            self.send_response(503);self.send_header('Content-Length','0');self.end_headers();return
        elif type(self).mode=='last-write' or type(self).mode=='bounded-caps' and (identifier in ('CH-signed-decimal','CH-binary-search-first') or identifier=='CH-stable-record-sort' and improved):
            used=sum(m.get('role')=='tool' for m in messages)
            rejected=['def solve(data):\n    return data.isdigit()\n','def solve(data):\n    return 1000001\n','import math\ndef solve(data):\n    return data\n','def solve(data):\n    return 10 ** 2\n']
            source=BY_ID[identifier]['reference'] if type(self).mode=='last-write' else rejected[max(0,used-2)%len(rejected)]
            name,args=('read_solution',{'path':'solution.py'}) if used==0 else ('write_solution',{'path':'solution.py','source':source}) if type(self).mode=='last-write' or used>=2 else ('run_tests',{})
            message={'role':'assistant','content':None,'tool_calls':[{'id':'cap-'+str(used),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        elif IMPROVED in str(messages):
            identifier=re.search(r'Task ID: (CH-[A-Za-z0-9-]+)',str(messages))[1]
            used=sum(m.get('role')=='tool' for m in messages)
            steps=[('read_solution',{'path':'solution.py'}),('write_solution',{'path':'solution.py','source':BY_ID[identifier]['reference']}),('run_tests',{})]
            if used<len(steps):
                name,args=steps[used];message={'role':'assistant','content':None,'tool_calls':[{'id':'tool-'+str(used),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
            else:message['content']='Repaired and ran public tests; independent tests remain pending.'
        reply={'model':body['model'],'choices':[{'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}]}
        raw=json.dumps(reply).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class ChallengeWorkflowTests(unittest.TestCase):
    def setUp(self):
        # These are required checks, not optional tests that silently skip pins.
        self.assertEqual(importlib.metadata.version('nanobot-ai'),'0.3.5')
        self.assertEqual(importlib.metadata.version('gepa'),'0.1.4')
        self.temp=tempfile.TemporaryDirectory();self.service=RuntimeService(self.temp.name)
        Model.calls=[];Model.mode='normal';self.server=ThreadingHTTPServer(('127.0.0.1',0),Model)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.service.ollama.save({**DEFAULTS,'host':'127.0.0.1','port':self.server.server_port,'model':'fixture-local','maxTokens':1024,'inferenceTimeout':10},0)
    def tearDown(self):
        outcome=getattr(getattr(self,'_outcome',None),'result',None)
        failed=outcome and any(case is self for case,_ in outcome.failures+outcome.errors)
        self.service.close();self.server.shutdown();self.server.server_close();self.thread.join()
        if failed:
            support=ROOT/'.local/test-reports/challenge-workflow'/uuid.uuid4().hex
            support.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(self.temp.name,support)
            print('CHALLENGE_TEST_SUPPORT',support,flush=True)
        self.temp.cleanup()
    def test_real_optimizer_repair_review_frozen_bank_edit_and_approval(self):
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(ROLES)]}
        # Explicit serial work: 22 rollouts, 6 calls each + 1 proposal, visible
        # tools (up to 24 per task), and three 5-second trusted verifier batches.
        rollouts=10+2*(3+3);calls=rollouts*6+1
        seconds=120+calls*10+rollouts*(24*5+3*5)+30
        print('CHALLENGE_FROZEN_BUDGET',json.dumps({'rollouts':rollouts,'calls':calls,'verificationBatches':3*rollouts,'workflowSeconds':seconds}),flush=True)
        run=self.service.start(registry,'challenge-proof','gepa-evolution',{'profile':'bank','bankRevision':1,'metricBudget':10,'proposalBudget':1,'taskCallBudget':6,'callTimeoutSeconds':10,'maxSeconds':seconds,'providerRevision':1,'expectedRevision':1})
        snapshot=run['gepaConfig']['datasetSnapshot'];before=json.dumps(snapshot,sort_keys=True)
        # Edit the live catalog after dispatch. The entire run must retain v1.
        question=dict(SEEDS[0]);question['title']='Edited after dispatch'
        self.service.challenges.mutate(1,question,question['id'])
        self.assertTrue(self.service.completion_event.wait(seconds+30),'No persisted terminal result')
        done=self.service.get_run(run['id']);self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult'];self.assertTrue(result['eligible']);self.assertEqual(result['selectedSkill']['body'],IMPROVED)
        self.assertEqual(result['final']['selected']['validation'],{'passed':3,'total':3})
        self.assertEqual(result['final']['selected']['heldout'],{'passed':3,'total':3})
        self.assertEqual(result['proposals'],1);self.assertIn('hard',result['breakdown']['difficulty'])
        # Accept the actual Python projection in the shipped JavaScript parser;
        # contradictory per-topic counts must fail before rendering.
        parser="""import fs from 'node:fs'; import {validateGepaRun} from './dist/js/runtime-client.js';
const run=JSON.parse(fs.readFileSync(0,'utf8'));validateGepaRun(run);
const row=Object.values(run.gepaResult.breakdown.topic)[0];row.selected.heldout.total+=1;
try{validateGepaRun(run);process.exit(1);}catch(e){if(!e.message.includes('分項'))throw e;}
"""
        parsed=subprocess.run(['node','--input-type=module','-e',parser],cwd=ROOT,input=json.dumps(done),text=True,capture_output=True,timeout=10)
        self.assertEqual(parsed.returncode,0,parsed.stdout+parsed.stderr)
        self.assertEqual(json.dumps(done['gepaConfig']['datasetSnapshot'],sort_keys=True),before)
        self.assertEqual(validate_snapshot(snapshot),snapshot['data'])
        directory=self.service.local/'runs'/run['id'];self.assertEqual(verify(directory),result)
        proposals=json.loads((directory/'gepa-proposals.json').read_text())
        train_ids={q['id'] for q in snapshot['data']['train']}
        self.assertTrue(all(t['taskId'] in train_ids for p in proposals for t in p['training']))
        for child in (directory/'rollouts').iterdir():
            cfg=json.loads((child/'repair-config.json').read_text())
            initial=json.loads((child/'repair-calls.json').read_text())[0]['request']['messages']
            self.assertNotIn(BY_ID[cfg['taskId']]['reference'],str(initial))
        approved=self.service.gepa.approve(run['id'],1);self.assertNotEqual(approved['activeVersionId'],'GSV-baseline')
        cfg_path=directory/'gepa-config.json';cfg=json.loads(cfg_path.read_text());cfg['datasetSnapshot']['data']['heldout'][0]['fixture']['hidden'][0]['expected']='tampered';cfg_path.write_text(json.dumps(cfg))
        with self.assertRaises(ValueError):verify(directory)

if __name__=='__main__':unittest.main()
