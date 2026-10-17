"""Complete Skill lineage, bounded queries and real diagnostic ZIP projections."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from skill_audit import Generation
from skill_archive import index, snapshot, candidate
from skill_engine import write
from export_diagnostics import build_bundle
from serve_gui import GuiHandler, DIST


class SkillArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'.local').mkdir()
        with sqlite3.connect(self.root/'.local/runtime.sqlite3') as db:
            db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,data TEXT,created TEXT)')
            db.execute('CREATE TABLE gepa_versions(id TEXT,run_id TEXT,data TEXT)')
        self.base={'name':'python-fix-and-verify','description':'Repair Python.','body':'Read and test.'}
        self.cfg={'baseline':{'id':'GSV-baseline','skill':self.base},'profile':'bank','bankRevision':3,
                  'metricBudget':10,'proposalBudget':8,'reflectionBatch':2,'callBudget':228,
                  'provider':{'config':{'provider':'strata','model':'fixture','apiKey':'PRIVATE_KEY','maxTokens':1024}},
                  'provenance':{'datasetVersion':'fixture-v1','datasetHash':'a'*64,'codeHashes':{'gepa_sdk.py':'b'*64}}}

    def tearDown(self):
        self.temp.cleanup()

    def run_record(self,number=1,task='gepa-evolution'):
        identifier=f'RUN-fixture-{number}'
        directory=self.root/'.local/runs'/identifier
        directory.mkdir(parents=True)
        cfgkey={'gepa-evolution':'gepaConfig','llm-evolution':'llmConfig','skill-evolution':'skillConfig'}[task]
        run={'id':identifier,'task':task,'status':'failed',cfgkey:self.cfg}
        with sqlite3.connect(self.root/'.local/runtime.sqlite3') as db:
            db.execute('INSERT INTO runs VALUES(?,?,?)',(identifier,json.dumps(run),f'2026-01-{number:02d}'))
        return identifier,directory

    def test_every_generated_unchanged_unselected_and_failed_body_has_conditions_and_diff(self):
        rid,directory=self.run_record()
        body='Check every boundary.\n'*90
        refs=[{'taskId':'TRAIN-1','rolloutId':'R0004','score':0,'source':'PRIVATE_SOURCE','expected':'PRIVATE_EXPECTED'}]
        with Generation(directory,'P001',self.cfg,self.base,refs,'gepa-worker',seed=0) as audit:
            audit.generated(candidate(self.base['body'],self.base))
        with Generation(directory,'P002',self.cfg,self.base,refs,'gepa-worker',seed=0,metricEvaluations=5) as audit:
            audit.generated(candidate(body,self.base))
        with self.assertRaises(ValueError):
            with Generation(directory,'P003',self.cfg,self.base,refs,'gepa-worker') as audit:
                audit.capture('Rejected Skill api_key=private-body-key')
                raise ValueError('Invalid candidate')
        write(directory/'gepa-proposals.json',[{'id':'P001','body':self.base['body'],'parentBody':self.base['body'],'training':refs},
                                               {'id':'P002','body':body,'parentBody':self.base['body'],'training':refs}])
        write(directory/'gepa-selection.json',{'skill':self.base})
        before={p:p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
            result=snapshot(self.root,rid)
        self.assertEqual(len(result['records']),3)
        first,second,failed=result['records']
        self.assertFalse(first['changed']);self.assertTrue(first['matchesSelection'])
        self.assertEqual(second['instruction']['text'],body)
        self.assertIn('+Check every boundary.',second['patch'])
        self.assertFalse(second['matchesSelection']);self.assertEqual(second['conditions']['metricEvaluations'],5)
        self.assertEqual(second['conditions']['model'],'fixture')
        self.assertEqual(second['conditions']['bankRevision'],3)
        self.assertEqual(failed['status'],'failed');self.assertTrue(failed['instruction']['redacted'])
        text=json.dumps(result)
        for secret in ('PRIVATE_KEY','PRIVATE_SOURCE','PRIVATE_EXPECTED','private-body-key'):
            self.assertNotIn(secret,text)
        self.assertEqual(before,{p:p.read_bytes() for p in directory.rglob('*') if p.is_file()})
        # The ZIP uses the same projector, retaining >1000-character instructions.
        raw=build_bundle(self.root,run_id=rid)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            exported=json.loads(z.read('skills/'+rid+'.json'))
            self.assertEqual(exported['records'][1]['instruction']['text'],body)
            content=b''.join(z.read(n) for n in z.namelist())
            for secret in (b'PRIVATE_KEY',b'PRIVATE_SOURCE',b'PRIVATE_EXPECTED',b'private-body-key'):
                self.assertNotIn(secret,content)
            self.assertEqual(json.loads(z.read('manifest.json'))['networkRequests'],0)

    def test_legacy_conditions_are_labeled_reconstructed_and_unknown_time_is_not_invented(self):
        rid,directory=self.run_record()
        write(directory/'gepa-proposals.json',[{'id':'P001','body':'New instructions','parentBody':self.base['body'],
                                               'createdAt':1234,'training':[{'taskId':'T1','score':0}]}])
        write(directory/'gepa-search.json',{'seed':7})
        result=snapshot(self.root,rid)
        record=result['records'][0]
        self.assertEqual(record['origin'],'reconstructed');self.assertIsNone(record['startedAt'])
        self.assertEqual(record['conditions']['seed'],7)
        self.assertIsNone(result['searchAudit'])

    def test_default_archive_includes_history_beyond_ten_recent_runs_and_reports_formal_versions(self):
        first=None
        for i in range(1,22):
            rid,directory=self.run_record(i)
            if first is None:first=rid
        with sqlite3.connect(self.root/'.local/runtime.sqlite3') as db:
            db.execute('INSERT INTO gepa_versions VALUES(?,?,?)',('GSV-one',first,json.dumps({'id':'GSV-one','label':'G1','skill':{'hash':'c'*64}})))
        self.assertEqual(len(index(self.root)['runs']),20)
        self.assertEqual(index(self.root,20)['runs'][0]['id'],first)
        self.assertEqual(snapshot(self.root,first)['approvedVersions'][0]['label'],'G1')
        with zipfile.ZipFile(io.BytesIO(build_bundle(self.root))) as z:
            self.assertIn('skills/'+first+'.json',z.namelist())
            self.assertEqual(json.loads(z.read('manifest.json'))['skillRuns'],{'total':21,'included':21})

    def test_incomplete_attempt_survives_and_overwrite_is_refused(self):
        rid,directory=self.run_record()
        audit=Generation(directory,'P001',self.cfg,self.base,[],'gepa-worker')
        audit.__enter__();audit.capture('Already returned')
        original=(directory/'skill-audit/P001.json').read_bytes()
        with Generation(directory,'P001',self.cfg,self.base,[],'gepa-worker') as duplicate:
            duplicate.generated(candidate('Must not overwrite',self.base))
        self.assertEqual((directory/'skill-audit/P001.json').read_bytes(),original)
        self.assertEqual(snapshot(self.root,rid)['records'][0]['status'],'returned')
        # Supplementary storage failure must not change the original result.
        with patch('skill_audit.save',return_value=False):
            with Generation(directory,'P002',self.cfg,self.base,[],'gepa-worker') as no_disk:
                no_disk.generated(candidate('Still valid',self.base))

    def test_interrupted_legacy_response_recovers_only_instruction_not_raw_training_or_request(self):
        rid,directory=self.run_record()
        (directory/'reflections/P001').mkdir(parents=True)
        write(directory/'reflections/P001/repair-calls.json',[{
            'status':'completed','startedAt':123,'finishedAt':124,
            'request':{'messages':[{'role':'system','content':'PRIVATE_SYSTEM'},
                {'role':'user','content':json.dumps({'candidate':{'skill_body':self.base['body']},
                    'training':[{'taskId':'TRAIN-1','score':0,'source':'PRIVATE_SOURCE','expected':'PRIVATE_EXPECTED'}]})}]},
            'response':{'choices':[{'message':{'content':json.dumps({'skill_body':'Recovered instructions'})}}]}}])
        result=snapshot(self.root,rid)
        record=result['records'][0]
        self.assertEqual(record['origin'],'recovered-response')
        self.assertEqual(record['status'],'returned')
        self.assertEqual(record['instruction']['text'],'Recovered instructions')
        self.assertEqual(record['trainingRefs'],[{'taskId':'TRAIN-1','score':0}])
        for secret in ('PRIVATE_SYSTEM','PRIVATE_SOURCE','PRIVATE_EXPECTED'):
            self.assertNotIn(secret,json.dumps(result))

    def test_symlink_and_input_budget_are_enforced(self):
        rid,directory=self.run_record()
        write(directory/'gepa-proposals.json','x'*100)
        result=snapshot(self.root,rid,input_budget=5)
        self.assertEqual(result['inputBytes'],5);self.assertTrue(result['warnings'])
        (directory/'skill-audit').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):snapshot(self.root,rid)
        for kwargs in ({'offset':-1},{'task':'other'}):
            with self.assertRaises(ValueError):index(self.root,**kwargs)

    def test_log_budget_reserves_space_for_skill_evidence(self):
        from diagnostic_log import DiagnosticLog
        rid,directory=self.run_record()
        write(directory/'gepa-proposals.json',[{'id':'P001','body':'Keep this Skill','parentBody':self.base['body'],'training':[]}])
        DiagnosticLog(self.root).write('startup','Budget fixture',extra='x'*1000)
        with patch('export_diagnostics.MAX_EXPORT',8*1024*1024+100):
            payload=build_bundle(self.root)
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            self.assertIn('skills/'+rid+'.json',z.namelist())
            manifest=json.loads(z.read('manifest.json'))
            self.assertTrue(any(o['file']=='startup.jsonl' for o in manifest['omitted']))

    def test_actual_http_query_origin_filters_and_selected_diagnostic_export(self):
        rid,_=self.run_record()
        class Quiet(GuiHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)))
        server.runtime=SimpleNamespace(root=self.root,local=self.root/'.local')
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            for route,headers,status in [('/api/v1/debug/skills',{},200),('/api/v1/debug/skills/'+rid,{},200),
                    ('/api/v1/debug/skills?task=unknown',{},503),('/api/v1/debug/skills?offset=0&offset=1',{},503),
                    ('/api/v1/debug/skills',{'Origin':'https://foreign.invalid'},403),
                    ('/api/v1/debug/support?runId='+rid,{},200)]:
                connection=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                connection.request('GET',route,headers=headers)
                response=connection.getresponse();payload=response.read();connection.close()
                self.assertEqual(response.status,status,route)
                if route.startswith('/api/v1/debug/support'):
                    with zipfile.ZipFile(io.BytesIO(payload)) as z:self.assertIn('skills/'+rid+'.json',z.namelist())
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
