"""Local metadata diagnostics: real sockets/processes, no external models."""
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import socket
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from debug_log import DebugLog
from diagnostic_log import DiagnosticLog, TransportTrace
from export_diagnostics import build_bundle
from ollama_bridge import OllamaBridge, DEFAULTS


def records(root, category):
    path=Path(root)/'.local/diagnostics'/(category+'.jsonl')
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@contextmanager
def model(mode='ok'):
    received=[];gate=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            if mode=='headers':gate.wait(5)
            raw=json.dumps({'model':'fixture:1','done':True,'load_duration':1000000}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            if mode=='body':gate.wait(5)
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port,received
    finally:gate.set();server.shutdown();server.server_close();thread.join()


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def bridge(self,port):
        bridge=OllamaBridge(self.root)
        bridge.save({**DEFAULTS,'host':'127.0.0.1','port':port,'model':'fixture:1'},0)
        self.addCleanup(bridge.close)
        return bridge

    def test_classification_redaction_and_role_bodies_stay_out_of_support(self):
        log=DebugLog(self.root)
        log.append('api','INFO','POST request',details={'prompt':'private-input','api_key':'credential-123'})
        log.append('worker','DEBUG','private-model-reply',details={'source':'subprocess','artifact':'worker.log'})
        log.append('llm','ERROR','call failed',details={'error':'Ollama HTTP 503: private-server-body'})
        log.append('ollama','INFO','Model preload started','WARM-fixture')
        text=''.join(p.read_text() for p in (self.root/'.local/diagnostics').glob('*.jsonl'))
        for value in ('private-input','credential-123','private-model-reply','private-server-body'):
            self.assertNotIn(value,text)
        self.assertTrue(records(self.root,'http'));self.assertTrue(records(self.root,'warmup'))
        self.assertTrue(records(self.root,'errors'))

    def test_process_writers_preserve_complete_json_lines_and_rotate(self):
        code="import sys;from diagnostic_log import DiagnosticLog;d=DiagnosticLog(sys.argv[1]);assert all(d.write('http','parallel',number=i) for i in range(25))"
        processes=[subprocess.Popen([sys.executable,'-c',code,str(self.root)],env={**__import__('os').environ,'PYTHONPATH':str(ROOT/'scripts')}) for _ in range(4)]
        for process in processes:self.assertEqual(process.wait(timeout=10),0)
        self.assertEqual(len(records(self.root,'http')),100)
        rotating=DiagnosticLog(self.root,maximum=1500,backups=2)
        for i in range(25):self.assertTrue(rotating.write('warmup','rotate',number=i))
        files=list(rotating.directory.glob('warmup.jsonl*'))
        self.assertEqual(len(files),3)
        self.assertTrue(all(p.stat().st_size<=1500 for p in files))
        for path in files:
            for line in path.read_text().splitlines():json.loads(line)

    def test_logging_failure_does_not_change_successful_http_result(self):
        (self.root/'.local').mkdir();(self.root/'.local/diagnostics').write_text('not a directory')
        with model() as (port,received):
            bridge=self.bridge(port)
            result=bridge.request(f'http://127.0.0.1:{port}','/api/generate',bridge.state()['config'],{'model':'fixture:1'})
            self.assertTrue(result['done']);self.assertEqual(len(received),1)

    def test_connection_refusal_records_connect_phase_and_errno(self):
        with socket.socket() as guard:
            guard.bind(('127.0.0.1',0));port=guard.getsockname()[1]
            bridge=self.bridge(port);trace=TransportTrace(self.root,category='warmup',correlation_id='WARM-fixture')
            with self.assertRaises(OSError):bridge.request(f'http://127.0.0.1:{port}','/api/generate',bridge.state()['config'],{'prompt':'private'},trace=trace)
        self.assertEqual(trace.failure['phase'],'connect.started')
        self.assertEqual(trace.failure['errno'],111)
        self.assertFalse(any(r['event']=='connect.completed' for r in records(self.root,'warmup')))

    def test_os_connection_timeout_preserves_errno_before_response(self):
        bridge=OllamaBridge(self.root);trace=TransportTrace(self.root,category='warmup')
        with patch('http.client.HTTPConnection.connect',side_effect=TimeoutError(110,'Connection timed out')):
            with self.assertRaises(OSError):bridge.request('http://127.0.0.1:1','/api/generate',DEFAULTS,{'model':'fixture:1'},trace=trace)
        self.assertEqual(trace.failure['errno'],110)
        self.assertEqual(trace.failure['phase'],'connect.started')
        self.assertIsNone(trace.status)

    def test_preload_startup_stderr_and_exit_code_survive_missing_result(self):
        bridge=self.bridge(1)
        original=subprocess.Popen
        def launch(command,**kwargs):
            return original([sys.executable,'-c','import sys;print("fixture-startup-error",file=sys.stderr);sys.exit(7)'],**kwargs)
        with patch('ollama_bridge.subprocess.Popen',side_effect=launch):
            bridge.start_warmup(1)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                job=bridge.warmup_status()
                if job['status']!='RUNNING':break
                time.sleep(.02)
        self.assertEqual(job['status'],'FAIL')
        rows=records(self.root,'warmup')
        self.assertTrue(any(r['event']=='worker.exited' and r['details']['exitCode']==7 for r in rows))
        self.assertIn('fixture-startup-error',json.dumps(rows))
        self.assertFalse(bridge.operation.locked())

    def test_header_and_body_stalls_have_distinct_observed_phases_and_no_retry(self):
        for mode,expected in [('headers','response.waiting'),('body','response.reading')]:
            with self.subTest(mode=mode),model(mode) as (port,received):
                trace=TransportTrace(self.root)
                config={**DEFAULTS,'host':'127.0.0.1','port':port,'model':'fixture:1','inferenceTimeout':1}
                bridge=OllamaBridge(self.root)
                with self.assertRaises(OSError):bridge.request(f'http://127.0.0.1:{port}','/api/generate',config,{'prompt':'private'},trace=trace)
                self.assertEqual(trace.failure['phase'],expected)
                self.assertEqual(len(received),1)
                self.assertEqual(trace.status,200 if mode=='body' else None)

    def test_real_preload_worker_failure_keeps_transport_after_cleanup(self):
        with socket.socket() as guard:
            guard.bind(('127.0.0.1',0));bridge=self.bridge(guard.getsockname()[1])
            bridge.start_warmup(1)
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                job=bridge.warmup_status()
                if job['status']!='RUNNING':break
                time.sleep(.02)
        self.assertEqual(job['status'],'FAIL',job)
        self.assertEqual(job['transport']['failure']['phase'],'connect.started')
        self.assertFalse(bridge.operation.locked())
        self.assertFalse(list(bridge.path.parent.glob(job['id']+'-*.json')))
        exported=build_bundle(self.root)
        with zipfile.ZipFile(io.BytesIO(exported)) as bundle:
            self.assertEqual(json.loads(bundle.read('status.json'))['warmup.json']['status'],'FAIL')
            self.assertIn('logs/warmup.jsonl',bundle.namelist())
            self.assertIn(b'connect.started',bundle.read('logs/warmup.jsonl'))

    def test_export_is_readonly_bounded_and_excludes_prompts_sources_and_symlinks(self):
        log=DiagnosticLog(self.root);log.write('startup','test')
        (self.root/'.local/diagnostics/warmup.jsonl').symlink_to(self.root/'external')
        (self.root/'external').write_text('private-external')
        (self.root/'.local/ollama').mkdir()
        (self.root/'.local/ollama/settings.json').write_text(json.dumps({'config':{'api_key':'private-key','model':'fixture:1'}}))
        with sqlite3.connect(self.root/'.local/runtime.sqlite3') as db:
            db.execute('CREATE TABLE runs(data TEXT,created TEXT)')
            db.execute('INSERT INTO runs VALUES(?,?)',(json.dumps({'id':'RUN-fixture','status':'failed','prompt':'private-prompt','source':'private-source'}),'now'))
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('export must not request HTTP')):
            raw=build_bundle(self.root)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            content=b''.join(bundle.read(n) for n in bundle.namelist())
            for value in (b'private-key',b'private-prompt',b'private-source',b'private-external'):self.assertNotIn(value,content)
            self.assertNotIn('logs/warmup.jsonl',bundle.namelist())
            self.assertEqual(json.loads(bundle.read('manifest.json'))['networkRequests'],0)

    def test_observed_state_changes_include_historical_identity_without_poll_noise(self):
        log=DiagnosticLog(self.root)
        snapshot={'latestRun':{'id':'RUN-previous','status':'failed','createdAt':'earlier','agents':[]}}
        log.observe(snapshot);log.observe(snapshot)
        self.assertEqual(len(records(self.root,'status')),1)
        snapshot['latestRun']={'id':'RUN-new','status':'running','agents':[]}
        log.observe(snapshot)
        self.assertEqual([r['details']['runId'] for r in records(self.root,'status')],['RUN-previous','RUN-new'])
        snapshot['repair']={'sdk':{'available':True,'version':'0.3.5'}}
        log.observe(snapshot)
        self.assertEqual(records(self.root,'status')[-1]['details']['sdk']['nanobot']['available'],True)

    def test_support_download_preserves_origin_guard_and_does_not_probe_sdk(self):
        from runtime_service import RuntimeService
        from serve_gui import GuiHandler,DIST
        runtime=RuntimeService(self.root)
        class Quiet(GuiHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));server.runtime=runtime
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}/api/v1/debug/support'
        try:
            with patch('sdk_runtime_probe.probe',side_effect=AssertionError('no SDK dispatch')):
                with urlopen(url,timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(),'application/zip')
                    with zipfile.ZipFile(io.BytesIO(response.read())) as bundle:self.assertIn('status.json',bundle.namelist())
            with self.assertRaises(HTTPError) as error:urlopen(Request(url,headers={'Origin':'http://elsewhere.invalid'}),timeout=5)
            self.assertEqual(error.exception.code,403)
        finally:server.shutdown();server.server_close();thread.join();runtime.close()

    def test_actual_service_boot_logs_startup_access_state_and_shutdown(self):
        dist=self.root/'dist';dist.mkdir();(dist/'index.html').write_text('fixture')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        code=f"import sys;from pathlib import Path;sys.path.insert(0,{str(ROOT/'scripts')!r});import serve_gui;serve_gui.DIST=Path({str(dist)!r});raise SystemExit(serve_gui.main(['--port',{str(port)!r}]))"
        with (self.root/'console.log').open('w') as output:
            process=subprocess.Popen([sys.executable,'-u','-c',code],stdout=output,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/api/v1/runtime',timeout=.5) as response:
                            self.assertIsNone(json.load(response)['latestRun'])
                        break
                    except OSError:
                        if process.poll() is not None:self.fail((self.root/'console.log').read_text())
                        time.sleep(.05)
                else:self.fail('service never became ready')
            finally:
                process.send_signal(signal.SIGINT)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait();self.fail('service did not stop')
        events=[r['event'] for r in records(self.root,'startup')]
        self.assertIn('service.starting',events);self.assertIn('service.ready',events);self.assertIn('service.stopped',events)
        self.assertTrue(records(self.root,'http'));self.assertTrue(records(self.root,'status'))

    def test_actual_bind_failure_is_saved_before_runtime_creation(self):
        dist=self.root/'dist';dist.mkdir();(dist/'index.html').write_text('fixture')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));reservation.listen();port=reservation.getsockname()[1]
            code=f"import sys;from pathlib import Path;sys.path.insert(0,{str(ROOT/'scripts')!r});import serve_gui;serve_gui.DIST=Path({str(dist)!r});raise SystemExit(serve_gui.main(['--port',{str(port)!r}]))"
            process=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(process.returncode,1)
        event=records(self.root,'errors')[-1]
        self.assertEqual(event['event'],'service.bind_failed')
        self.assertEqual(event['details']['errno'],98)
        self.assertFalse((self.root/'.local/runtime.sqlite3').exists())
