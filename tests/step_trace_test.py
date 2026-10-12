"""Small-step regression for structured tracing and isolated batch evaluation."""
import asyncio
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from debug_log import DebugLog
from step_trace import Step,traced,snapshot
from repair_engine import trusted_test,trusted_test_batch,ROOT
from repair_fixture import BASELINE
from serve_gui import GuiHandler,DIST

GOOD='def clamp(value, lower, upper):\n    if lower > upper:\n        raise ValueError("bounds")\n    return max(lower,min(value,upper))\n'
class StepTests(unittest.TestCase):
    def test_start_finish_failure_redaction_and_duration(self):
        with tempfile.TemporaryDirectory() as root:
            logs=DebugLog(root)
            with Step(logs,'gepa','prepare','RUN-test',taskId='PY-test'):pass
            with self.assertRaises(ValueError),Step(logs,'gepa','evaluate','RUN-test'):raise ValueError('token=private-value')
            records=logs.list(run_id='RUN-test')['records'];self.assertEqual(len(records),4)
            self.assertEqual(records[0]['details']['event'],'STEP_FAILED');self.assertGreaterEqual(records[0]['details']['durationMs'],0)
            self.assertNotIn('private-value',json.dumps(records));self.assertEqual(records[-1]['details']['event'],'STEP_STARTED')
    def test_journal_failure_does_not_change_return_or_exception(self):
        class Broken:
            def append(self,*a,**k):raise OSError('disk unavailable')
        with Step(Broken(),'gepa','check'):value=42
        self.assertEqual(value,42)
        with self.assertRaisesRegex(ValueError,'original'),Step(Broken(),'gepa','check'):raise ValueError('original')
    def test_sync_async_method_context_and_safe_argument_selection(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'.local/runs/RUN-test';directory.mkdir(parents=True)
            (directory/'repair-config.json').write_text(json.dumps({'logRoot':root,'runId':'RUN-test'}))
            @traced('nanobot','sync')
            def operation(directory,role):return role
            @traced('nanobot','async')
            async def async_operation(directory):return 7
            class Runner:
                def __init__(self):self.directory=directory;self.config={'logRoot':root}
                @traced('nanobot','tool.execute')
                def tool(self,name,arguments):return 9
            self.assertEqual(operation(directory,'worker'),'worker');self.assertEqual(asyncio.run(async_operation(directory)),7)
            self.assertEqual(Runner().tool('write_solution',{'source':'PRIVATE_SOURCE'}),9)
            rows=DebugLog(root).list(run_id='RUN-test')['records'];self.assertEqual(len(rows),6)
            self.assertEqual(rows[0]['details']['toolName'],'write_solution');self.assertNotIn('PRIVATE_SOURCE',json.dumps(rows))
    def test_summary_pairs_events_and_marks_unreported_terminal_spans(self):
        with tempfile.TemporaryDirectory() as root:
            logs=DebugLog(root);Step(logs,'nanobot','killed-turn','RUN-test')
            with Step(logs,'runtime','role.process','RUN-test'):pass
            class Service:
                def get_run(self,id):return {'status':'cancelled'}
            service=Service();service.logs=logs;data=snapshot(service,'RUN-test')
            self.assertEqual(len(data['steps']),2);self.assertEqual({s['status'] for s in data['steps']},{'unreported','completed'})
            self.assertFalse(data['truncated'])
    def test_journal_retention_reports_partial_history(self):
        with tempfile.TemporaryDirectory() as root:
            logs=DebugLog(root,retention=1)
            with Step(logs,'gepa','last-step','RUN-test'):pass
            class Service:
                def get_run(self,id):return {'status':'completed'}
            service=Service();service.logs=logs;data=snapshot(service,'RUN-test')
            self.assertIsNone(data['steps'][0]['startedAt']);self.assertEqual(data['steps'][0]['status'],'completed')

class BatchTests(unittest.TestCase):
    def test_batch_matches_single_case_evidence_and_resets_namespace(self):
        jobs=[{'source':body,'split':split} for body in (BASELINE,GOOD,BASELINE) for split in ('visible','hidden')]
        result=trusted_test_batch(jobs)
        self.assertEqual(result,[trusted_test(j['source'],j['split']) for j in jobs])
        self.assertEqual(result[0],result[4]);self.assertEqual(result[2]['passed'],6)
    def test_four_result_jobs_launch_one_isolated_process(self):
        jobs=[{'source':body,'split':split} for body in (BASELINE,GOOD) for split in ('visible','hidden')]
        with patch('repair_engine.subprocess.run',wraps=subprocess.run) as calls:
            rows=trusted_test_batch(jobs)
        self.assertEqual(len(rows),4);self.assertEqual(calls.call_count,1)
        self.assertIn('-I',calls.call_args.args[0]);self.assertIn('-S',calls.call_args.args[0])
    def test_invalid_batches_syntax_and_limits_fail_closed(self):
        for jobs in ([],[{'source':GOOD,'split':'unknown'}],[{'source':GOOD,'split':'visible'}]*33,[{'source':'import os','split':'visible'}]):
            with self.subTest(jobs=str(jobs)[:70]),self.assertRaises(ValueError):trusted_test_batch(jobs)
        with self.assertRaises(ValueError):trusted_test_batch([{'source':'x'*1000001,'split':'visible'}])
    def test_malformed_child_output_or_missing_result_is_rejected(self):
        for raw in ('not JSON','{"results":[]}','{"error":"invalid job"}'):
            with patch('repair_engine.subprocess.run',return_value=subprocess.CompletedProcess([],0,raw,'')),self.assertRaises(ValueError):trusted_test_batch([{'source':GOOD,'split':'visible'}])

class StepApiTests(unittest.TestCase):
    def test_real_http_read_only_route_preserves_origin_and_unknown_run_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            class Service:
                csrf_token='local-token'
                def get_run(self,id):
                    if id!='RUN-test':raise KeyError('Run not found')
                    return {'status':'completed'}
            service=Service();service.logs=DebugLog(root)
            with Step(service.logs,'gepa','search','RUN-test'):pass
            class Quiet(GuiHandler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));server.runtime=service
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                for path,headers,status in [('/api/v1/debug/steps/RUN-test',{},200),('/api/v1/debug/steps/RUN-missing',{},404),('/api/v1/debug/steps/RUN-test',{'Origin':'https://outside.example'},403),('/api/v1/debug/steps/not-a-run',{},404)]:
                    conn=HTTPConnection('127.0.0.1',server.server_port);conn.request('GET',path,headers=headers);response=conn.getresponse();data=json.loads(response.read());conn.close()
                    self.assertEqual(response.status,status)
                    if status==200:self.assertEqual(data['steps'][0]['name'],'search')
            finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
