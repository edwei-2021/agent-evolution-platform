"""Real loopback model preload and supervised worker cancellation/deadlines."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_service import RuntimeService, ROLES
from adaptive_validation import current as validation_calibration
from validation_wait import startup_budget
from ollama_bridge import DEFAULTS

class Model(BaseHTTPRequestHandler):
    calls=[];gate=None;entered=threading.Event();mode='ok'
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path,body));self.entered.set()
        if self.gate:self.gate.wait(10)
        value={'model':body['model'],'done':self.mode!='bad','load_duration':3500000000,'total_duration':4000000000}
        if self.mode=='error':value={'error':'mock preload failed'}
        raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass

class WarmupTests(unittest.TestCase):
    def setUp(self):
        self.io_seconds=validation_calibration()['perCallIoAllowanceSeconds']
        Model.calls=[];Model.gate=None;Model.entered.clear();Model.mode='ok'
        self.temp=tempfile.TemporaryDirectory();self.service=RuntimeService(self.temp.name);self.bridge=self.service.ollama
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Model);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.bridge.save({**DEFAULTS,'host':'127.0.0.1','port':self.server.server_port,'model':'qwen3-coder:30b'},0)
    def tearDown(self):
        if Model.gate:Model.gate.set()
        self.service.close();self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def finish(self):
        deadline=time.monotonic()+max(10,5+5*self.io_seconds)
        while time.monotonic()<deadline:
            job=self.bridge.warmup_status()
            if job['status']!='RUNNING':return job
            time.sleep(.02)
        self.fail('preload did not terminate')

    def test_completed_preload_is_not_visible_until_cleanup_and_slot_release(self):
        finalizing = threading.Event()
        resume = threading.Event()
        original = self.bridge.logs.append
        def pause_final_log(module, level, message, *args, **kwargs):
            if message.startswith('Model preload PRELOAD_PASS'):
                finalizing.set()
                if not resume.wait(10):
                    raise AssertionError('Finalization barrier was not released')
            return original(module, level, message, *args, **kwargs)
        with patch.object(self.bridge.logs, 'append', side_effect=pause_final_log):
            try:
                self.bridge.start_warmup(1)
                self.assertTrue(finalizing.wait(startup_budget(self.io_seconds, 600)))
                self.assertEqual(self.bridge.warmup_status()['status'], 'RUNNING')
                self.assertTrue(self.bridge.operation.locked())
                with self.assertRaises(RuntimeError):
                    self.bridge.start_warmup(1)
            finally:
                resume.set()
            job = self.finish()
        self.assertEqual(job['status'], 'PRELOAD_PASS')
        self.assertFalse(self.bridge.operation.locked())
        self.assertFalse(list(self.bridge.path.parent.glob(job['id']+'-*.json')))
        self.assertEqual(self.service.logs.list(module='ollama',run_id=job['id'])['matched'],2)

    def test_deadline_clock_stops_real_worker_after_observed_dispatch_without_retry(self):
        self.bridge.save({**self.bridge.state()['config'], 'inferenceTimeout':30}, 1)
        Model.gate = threading.Event()
        clock = SimpleNamespace(time=time.time,
            monotonic=lambda:time.monotonic() + (31 if Model.entered.is_set() else 0))
        # Advance only the bridge clock after the actual HTTP request. Startup
        # speed cannot decide whether the supervisor's absolute limit is tested.
        with patch('ollama_bridge.time', clock):
            self.bridge.start_warmup(2)
            job = self.finish()
        self.assertTrue(Model.entered.is_set())
        self.assertEqual(job['timeoutSeconds'],30)
        self.assertEqual(job['status'],'FAIL')
        self.assertIn('absolute limit',job['error'])
        self.assertEqual(len(Model.calls),1)
        self.assertFalse(self.bridge.operation.locked())
        with self.assertRaises(ProcessLookupError):
            os.kill(job['pid'],0)

    def test_explicit_preload_has_no_prompt_generation_and_is_persisted_separately(self):
        self.assertEqual(Model.calls,[]);self.bridge.snapshot();self.assertEqual(Model.calls,[])
        self.bridge.start_warmup(1);job=self.finish()
        self.assertEqual(job['status'],'PRELOAD_PASS');self.assertEqual(job['loadDurationMs'],3500)
        self.assertEqual(Model.calls,[('/api/generate',{'model':'qwen3-coder:30b','prompt':'','stream':False,'keep_alive':'15m'})])
        self.assertIsNone(self.bridge.snapshot()['latest']);self.assertFalse(self.bridge.operation.locked())
        self.assertEqual(self.service.logs.list(module='ollama',run_id=job['id'])['matched'],2)
        self.service.close();self.service=RuntimeService(self.temp.name);self.bridge=self.service.ollama
        self.assertEqual(self.bridge.warmup_status()['status'],'PRELOAD_PASS');self.assertEqual(len(Model.calls),1)

    def test_preload_blocks_overlap_and_cancels_without_unload_or_retry(self):
        Model.gate=threading.Event();job=self.bridge.start_warmup(1)
        wait_seconds=startup_budget(self.io_seconds,600)
        print(f'WARMUP_REQUEST_EXPECTED maximum_startup_seconds={wait_seconds}',flush=True)
        elapsed=0
        while elapsed<wait_seconds and not Model.entered.wait(min(10,wait_seconds-elapsed)):
            elapsed+=min(10,wait_seconds-elapsed)
            print(f'WARMUP_REQUEST_WAIT elapsed_seconds={elapsed} status={self.bridge.warmup_status()["status"]}',flush=True)
        self.assertTrue(Model.entered.is_set(),self.bridge.warmup_status())
        with self.assertRaises(RuntimeError):self.bridge.start_warmup(1)
        with self.assertRaises(RuntimeError):self.bridge.run('metadata',1)
        registry={'agents':[{'id':'AG-'+str(i),'name':r,'role':r,'enabled':True} for i,r in enumerate(ROLES)]}
        with self.assertRaises(RuntimeError):self.service.start(registry,'overlap','llm-evolution',{'profile':'smoke','maxSeconds':60,'expectedRevision':1,'providerRevision':1})
        self.bridge.cancel_warmup(job['id']);done=self.finish()
        self.assertEqual(done['status'],'CANCELLED');self.assertEqual(len(Model.calls),1);self.assertFalse(self.bridge.operation.locked())
        self.assertIn('Local preload stopped',done['error'])

    def test_absolute_warmup_timeout_releases_slot_and_logs_failure(self):
        self.bridge.save({**self.bridge.state()['config'],'inferenceTimeout':1},1)
        Model.gate=threading.Event();self.bridge.start_warmup(2);job=self.finish()
        self.assertEqual(job['status'],'FAIL');self.assertEqual(job['timeoutSeconds'],1)
        self.assertLessEqual(len(Model.calls),1)  # cold startup may expire before HTTP dispatch; never retry
        self.assertTrue(job['error']);self.assertFalse(self.bridge.operation.locked())
        self.assertEqual(self.service.logs.list(module='ollama',level='ERROR',run_id=job['id'])['matched'],1)

    def test_invalid_stale_and_malformed_requests_never_claim_preload_success(self):
        for revision,keep in [(0,15),(True,15),(1,True),(1,0),(1,61)]:
            with self.assertRaises((ValueError,RuntimeError)):self.bridge.start_warmup(revision,keep)
        self.assertEqual(Model.calls,[]);self.assertFalse(self.bridge.operation.locked())
        for mode in ('bad','error'):
            Model.mode=mode;self.bridge.start_warmup(1);self.assertEqual(self.finish()['status'],'FAIL')
        self.assertEqual(len(Model.calls),2)

    def test_service_restart_marks_old_active_preload_unconfirmed_without_dispatch(self):
        from ollama_bridge import atomic_write
        job={'id':'WARM-old','status':'RUNNING','startedAt':self.service.timestamp(),'config':self.bridge.state()['config'],'revision':1,'timeoutSeconds':600}
        atomic_write(self.bridge.path.parent/'warmup.json',json.dumps(job))
        self.bridge.recover_warmup();self.assertEqual(self.bridge.warmup_status()['status'],'INTERRUPTED');self.assertEqual(Model.calls,[])
