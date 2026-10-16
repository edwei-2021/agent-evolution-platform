"""Completion policy, real SDK looping fixtures and body-free diagnostic export."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import sqlite3
import zipfile
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repair_test
from repair_engine import RepairRunner, summary_ready, source_hash, verify, SUMMARY_MESSAGE
from repair_fixture import BASELINE
from repair_fixture import TOOLS
from export_diagnostics import repair_summary, build_bundle

class RepeatingModel(BaseHTTPRequestHandler):
    calls=[];mode='ok'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.calls.append(body)
        n=len(self.calls);name,args,content=None,None,None
        if not body['tools'] and self.mode!='ignore-final':
            content='Repaired the bounds and reversed-range error; visible tests passed.'
        elif self.mode=='budget' or n==1:name,args='read_solution',{'path':'solution.py'}
        elif n==2:name,args='run_tests',{}
        elif n==3:
            source=repair_test.GOOD
            if self.mode=='hidden-regression':source=source.replace('    return max(', '    if value < 0:\n        return 0\n    return max(')
            name,args='write_solution',{'path':'solution.py','source':source}
        else:name,args='run_tests',{}
        message={'role':'assistant','content':content}
        if name:message['tool_calls']=[{'id':f'call_{n}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]
        finish='tool_calls' if name else 'length' if self.mode=='truncated-final' else 'stop'
        reply={'model':body['model'],'choices':[{'message':message,'finish_reason':finish}]}
        raw=json.dumps(reply).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class CompletionUnitTests(unittest.TestCase):
    def test_only_passing_tests_of_the_current_source_authorize_summary(self):
        def event(passed,total=6,body=repair_test.GOOD):
            return {'name':'run_tests','status':'completed','sourceHash':source_hash(body),'result':json.dumps({'split':'visible','passed':passed,'total':total})}
        self.assertFalse(summary_ready([],repair_test.GOOD))
        self.assertFalse(summary_ready([event(3)],repair_test.GOOD))
        self.assertFalse(summary_ready([event(0,0)],repair_test.GOOD))
        self.assertFalse(summary_ready([event(True,True)],repair_test.GOOD))
        self.assertFalse(summary_ready([event(6)],BASELINE))
        self.assertTrue(summary_ready([event(6)],repair_test.GOOD))
        self.assertFalse(summary_ready([event(6),{'name':'run_tests','status':'failed'}],repair_test.GOOD))
    def test_source_mutation_reopens_tools_and_support_summary_never_exports_bodies(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'.local/runs/RUN-fixture';directory.mkdir(parents=True)
            (directory/'task-workspace').mkdir();(directory/'task-workspace/solution.py').write_text(repair_test.GOOD)
            cfg={'provider':{'config':{'model':'fixture','maxTokens':256,'inferenceTimeout':10},'endpoint':'http://127.0.0.1:1'},'logRoot':root}
            runner=RepairRunner(directory,cfg);runner.tool('run_tests',{})
            self.assertTrue(summary_ready(runner.tools,repair_test.GOOD))
            runner.tool('write_solution',{'path':'solution.py','source':BASELINE})
            self.assertFalse(summary_ready(runner.tools,BASELINE))
            (directory/'repair-calls.json').write_text(json.dumps([{'id':1,'status':'completed','request':{'messages':'private-prompt'},'response':{'choices':[{'finish_reason':'tool_calls','message':{'content':'private-answer'}}]}}]))
            (directory/'repair-sdk-result.json').write_text(json.dumps({'stopReason':'max_iterations','messages':'private-transcript'}))
            summary=repair_summary(directory);text=json.dumps(summary)
            self.assertEqual(summary['tools'][0]['visiblePassed'],6);self.assertEqual(summary['sdkStopReason'],'max_iterations')
            for secret in ('private-prompt','private-answer','private-transcript',BASELINE,repair_test.GOOD):self.assertNotIn(secret,text)
            (directory/'repair-tools.json').unlink();(directory/'repair-tools.json').symlink_to(directory/'repair-calls.json')
            self.assertNotIn('tools',repair_summary(directory))

    def test_archive_keeps_scores_and_stop_reason_after_redaction(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'.local/runs/RUN-fixture';directory.mkdir(parents=True)
            (directory/'repair-tools.json').write_text(json.dumps([{'id':1,'name':'run_tests','status':'completed','result':json.dumps({'passed':6,'total':6,'records':'private-test-inputs'})}]))
            (directory/'repair-sdk-result.json').write_text(json.dumps({'stopReason':'max_iterations','messages':'private-prompt'}))
            with sqlite3.connect(Path(root)/'.local/runtime.sqlite3') as db:
                db.execute('CREATE TABLE runs(created REAL,data TEXT)')
                db.execute('INSERT INTO runs VALUES(?,?)',(1,json.dumps({'id':'RUN-fixture','task':'nanobot-repair','repairConfig':{'provider':{'config':{'maxTokens':256}}}})))
            with zipfile.ZipFile(io.BytesIO(build_bundle(root))) as archive:
                status=json.loads(archive.read('status.json'));run=status['runs'][0]
                self.assertEqual(run['repairTrace']['tools'][0]['visiblePassed'],6)
                self.assertEqual(run['repairTrace']['sdkStopReason'],'max_iterations')
                self.assertEqual(run['limits']['outputLimit'],256)
                self.assertNotIn('private-',archive.read('status.json').decode())

    def test_mutation_during_test_does_not_qualify_the_replacement_source(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'run';path=directory/'task-workspace/solution.py';path.parent.mkdir(parents=True);path.write_text(repair_test.GOOD)
            runner=RepairRunner(directory,{'logRoot':root})
            def change(source,*args):
                self.assertEqual(source,repair_test.GOOD);path.write_text(BASELINE)
                return {'split':'visible','passed':6,'total':6,'records':[]}
            with patch('repair_engine.trusted_test',side_effect=change):runner.tool('run_tests',{})
            self.assertEqual(runner.tools[0]['sourceHash'],source_hash(repair_test.GOOD))
            self.assertFalse(summary_ready(runner.tools,path.read_text()))

    def test_malformed_response_keeps_the_original_failure_through_logging(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'run';path=directory/'task-workspace/solution.py';path.parent.mkdir(parents=True);path.write_text(BASELINE)
            cfg={'logRoot':root,'callBudget':8,'callTimeoutSeconds':10,'deadlineEpoch':time.time()+60,
                 'provider':{'endpoint':'http://127.0.0.1:1','config':{'model':'fixture','maxTokens':256,'inferenceTimeout':10}}}
            runner=RepairRunner(directory,cfg)
            with patch('repair_engine.stream_chat',return_value=([],None)):
                with self.assertRaises(TypeError):runner.call([], [{'function':{'name':name}} for name in TOOLS])
            self.assertEqual(runner.calls[0]['status'],'failed');self.assertIn('indices',runner.calls[0]['error'])

@unittest.skipUnless(repair_test.SDK,'Requires pinned nanobot SDK')
class CompletionSdkTests(unittest.TestCase):
    def setUp(self):
        self.f=repair_test.SdkWorkflowTests('test_real_sdk_repair_tools_independent_scores_and_evidence')
        self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.model.shutdown();self.f.model.server_close();self.f.thread.join()
        RepeatingModel.calls=[];RepeatingModel.mode='ok'
        self.f.model=ThreadingHTTPServer(('127.0.0.1',0),RepeatingModel)
        self.f.thread=threading.Thread(target=self.f.model.serve_forever,daemon=True);self.f.thread.start()
        config=self.f.service.ollama.state()['config'];self.f.service.ollama.save({**config,'port':self.f.model.server_port},1)
        from runtime_service import ROLES
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(ROLES)]}
        self.f.start=lambda budget=8:self.f.service.start(registry,'completion-test','nanobot-repair',
            {'maxSeconds':self.f.workflow_seconds,'callTimeoutSeconds':10,'callBudget':budget,'providerRevision':2})
    def test_repeating_model_is_switched_to_one_summary_within_the_original_budget(self):
        done=self.f.finish(self.f.start()['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        self.assertEqual(len(RepeatingModel.calls),5);self.assertEqual(RepeatingModel.calls[-1]['tools'],[])
        self.assertNotIn('tool_choice',RepeatingModel.calls[-1])
        self.assertEqual(RepeatingModel.calls[-1]['messages'][-1],SUMMARY_MESSAGE)
        self.assertTrue(done['repairResult']['repairPassed']);self.assertEqual(done['repairResult']['candidate']['hidden']['passed'],6)
        directory=self.f.service.local/'runs'/done['id'];self.assertEqual(verify(directory),done['repairResult'])
        trace=repair_summary(directory);self.assertEqual(trace['sdkStopReason'],'completed');self.assertTrue(trace['calls'][-1]['finalSummary'])
        calls=json.loads((directory/'repair-calls.json').read_text());calls[-1]['request']['tools']=calls[0]['request']['tools'];(directory/'repair-calls.json').write_text(json.dumps(calls))
        with self.assertRaisesRegex(ValueError,'summary request policy'):verify(directory)
    def test_visible_pass_allows_summary_but_hidden_regression_still_fails_repair(self):
        RepeatingModel.mode='hidden-regression';done=self.f.finish(self.f.start()['id'])
        self.assertEqual(done['status'],'completed',done.get('error'));self.assertEqual(len(RepeatingModel.calls),5)
        self.assertEqual(done['repairResult']['candidate']['visible']['passed'],6)
        self.assertFalse(done['repairResult']['repairPassed']);self.assertLess(done['repairResult']['candidate']['hidden']['passed'],6)
    def test_server_ignoring_no_tools_fails_without_executing_an_extra_tool(self):
        RepeatingModel.mode='ignore-final';done=self.f.finish(self.f.start()['id'])
        self.assertEqual(done['status'],'failed');self.assertEqual(len(RepeatingModel.calls),5)
        directory=self.f.service.local/'runs'/done['id'];self.assertEqual(len(json.loads((directory/'repair-tools.json').read_text())),4)
        self.assertFalse(self.f.service.ollama.operation.locked())
    def test_truncated_summary_is_a_failure(self):
        RepeatingModel.mode='truncated-final';done=self.f.finish(self.f.start()['id'])
        self.assertEqual(done['status'],'failed');self.assertEqual(len(RepeatingModel.calls),5)
    def test_no_passing_tests_preserves_the_absolute_cap_and_max_iterations_failure(self):
        RepeatingModel.mode='budget';done=self.f.finish(self.f.start(2)['id'])
        self.assertEqual(done['status'],'failed');self.assertEqual(len(RepeatingModel.calls),2)
        directory=self.f.service.local/'runs'/done['id'];sdk=json.loads((directory/'repair-sdk-result.json').read_text())
        self.assertEqual(sdk['stopReason'],'max_iterations');self.assertTrue(all(c['tools'] for c in RepeatingModel.calls))

if __name__=='__main__':unittest.main()
