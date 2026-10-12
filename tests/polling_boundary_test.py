"""Slow progress reads cannot hold supervisor lock; disconnected HTTP is terminal."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_service import RuntimeService
from serve_gui import GuiHandler

class PollingBoundaryTests(unittest.TestCase):
    def test_slow_decoration_does_not_block_supervisor_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RuntimeService.__new__(RuntimeService)
            service.db = Path(directory)/'runtime.sqlite3'
            service.lock = threading.RLock()
            with sqlite3.connect(service.db) as db:
                db.execute('CREATE TABLE runs(id TEXT,data TEXT)')
                db.execute('INSERT INTO runs VALUES(?,?)',('run',json.dumps({'id':'run'})))
            entered, release = threading.Event(), threading.Event()
            def slow(run):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test gate timed out')
                return run
            service.decorate = slow
            result = []
            worker = threading.Thread(target=lambda:result.append(service.get_run('run')))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                acquired = service.lock.acquire(blocking=False)
                if acquired:
                    service.lock.release()
                self.assertTrue(acquired,'Read polling holds the supervisor lock')
            finally:
                release.set()
                worker.join(5)
            self.assertEqual(result,[{'id':'run'}])

    def test_disconnected_response_is_not_retried(self):
        for error in (BrokenPipeError,ConnectionResetError):
            with self.subTest(error=error):
                handler = GuiHandler.__new__(GuiHandler)
                handler.server = object()
                handler.path = '/api/v1/runtime'
                handler.command = 'GET'
                calls = []
                handler.send_response = lambda status:calls.append(status)
                handler.send_header = lambda *args:None
                handler.end_headers = lambda:None
                class Closed:
                    def write(self,data):
                        raise error('disconnected')
                handler.wfile = Closed()
                handler.json_response(200,{'state':'running'})
                self.assertEqual(calls,[200])
                self.assertTrue(handler.close_connection)

    def test_non_disconnect_write_error_is_not_swallowed(self):
        handler = GuiHandler.__new__(GuiHandler)
        handler.server = object()
        handler.path,handler.command = '/api/v1/runtime','GET'
        handler.send_response = lambda status:None
        handler.send_header = lambda *args:None
        handler.end_headers = lambda:None
        class Broken:
            def write(self,data):
                raise OSError('unrelated transport error')
        handler.wfile = Broken()
        with self.assertRaises(OSError):
            handler.json_response(200,{})
