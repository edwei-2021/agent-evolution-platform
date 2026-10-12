"""Persistent journal filters, retention and local API access; no Windows calls."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from debug_log import DebugLog
from runtime_service import RuntimeService
from serve_gui import GuiHandler, DIST

class JournalTests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.log = DebugLog(self.temp.name, retention=20)
    def tearDown(self): self.temp.cleanup()

    def test_retention_filtered_cursor_and_restart(self):
        for i in range(35): self.log.append('llm', 'ERROR' if i % 2 else 'INFO', f'call {i}', 'RUN-one' if i % 3 else 'RUN-two')
        page = self.log.list(level='ERROR', run_id='RUN-one', query='CALL', limit=3)
        self.assertEqual(page['retained'], 20); self.assertEqual(len(page['records']), 3)
        older = self.log.list(level='ERROR', run_id='RUN-one', query='CALL', before=page['nextBefore'], limit=3)
        self.assertTrue(all(r['id'] < page['nextBefore'] for r in older['records']))
        self.assertEqual(page['matched'], older['matched'])
        self.assertEqual(DebugLog(self.temp.name).list()['retained'], 20)
        for kwargs in [{'module': 'unknown'}, {'limit': 501}, {'before': 0}, {'query': 'x' * 201}]:
            with self.assertRaises(ValueError): self.log.list(**kwargs)
        self.assertEqual(self.log.list(query="' OR 1=1 --")['records'], [])

    def test_redaction_size_bounds_and_no_prompt_content(self):
        self.log.append('gui', 'ERROR', 'Authorization: Bearer abc123 token=def456 password=xyz', details={
            'api_key':'top-secret','prompt':'private prompt','nested':{'content':'private answer'},'reasoningChars':17,'debug':'x'*10000})
        record = self.log.list()['records'][0]; text = json.dumps(record)
        for secret in ('abc123','def456','xyz','top-secret','private prompt','private answer'): self.assertNotIn(secret, text)
        self.assertEqual(record['details']['reasoningChars'], 17)
        self.assertLess(len(text), 7000)

    def test_concurrent_writers_keep_unique_records(self):
        writers = [threading.Thread(target=lambda: [self.log.append('api','INFO','request') for _ in range(20)]) for _ in range(3)]
        for t in writers: t.start()
        for t in writers: t.join()
        page=self.log.list();self.assertEqual(page['retained'],20)
        ids=[r['id'] for r in page['records']];self.assertEqual(len(set(ids)),20)

    def test_unavailable_journal_does_not_break_operations(self):
        root=Path(self.temp.name)/'broken';(root/'.local').mkdir(parents=True)
        (root/'.local/debug.sqlite3').write_bytes(b'not a sqlite database')
        broken=DebugLog(root)
        self.assertFalse(broken.append('llm','INFO','call completed'))
        with self.assertRaises(OSError): broken.list()

class JournalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.runtime=RuntimeService(self.temp.name)
        class Quiet(GuiHandler):
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));self.server.runtime=self.runtime
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.runtime.close();self.temp.cleanup()
    def request(self,path,body=None,token=True,origin=None):
        headers={'Content-Type':'application/json','Origin':origin or self.base}
        if token:headers['X-Lab-Token']=self.runtime.csrf_token
        with urlopen(Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5) as r:return json.load(r)

    def test_browser_error_record_and_filters_without_request_secrets(self):
        body={'level':'ERROR','message':'fetch failed token=do-not-store','page':'llm'}
        with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/logs',body,False)
        self.assertEqual(exc.exception.code,403)
        self.request('/api/v1/debug/logs',body)
        page=self.request('/api/v1/debug/logs?module=gui&level=ERROR&q=fetch')
        self.assertEqual(len(page['records']),1);self.assertNotIn('do-not-store',json.dumps(page))
        self.assertNotIn(self.runtime.csrf_token,json.dumps(self.request('/api/v1/debug/logs')))
        with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/logs',origin='http://evil.test')
        self.assertEqual(exc.exception.code,403)
        for query in ('limit=999','module=unknown','q=a&q=b','file=/etc/passwd'):
            with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/logs?'+query)
            self.assertEqual(exc.exception.code,400)
        self.runtime.logs.available=False
        with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/logs',body)
        self.assertEqual(exc.exception.code,503)
        self.assertIsNone(self.runtime.snapshot()['latestRun'])

    def test_legacy_role_log_is_readonly_bounded_and_symlinks_are_rejected(self):
        run={'id':'RUN-legacy','requestId':'legacy','createdAt':self.runtime.timestamp(),'updatedAt':self.runtime.timestamp(),'status':'completed','agents':[]}
        with self.runtime.connect() as db:db.execute('INSERT INTO runs VALUES (?,?,?,?)',(run['id'],run['requestId'],json.dumps(run),run['createdAt']))
        directory=self.runtime.local/'runs'/run['id'];directory.mkdir(parents=True)
        (directory/'worker.log').write_text('x'*200001+'\nlegacy error')
        result=self.request('/api/v1/debug/runs/RUN-legacy/worker')
        self.assertTrue(result['truncated']);self.assertEqual(len(result['content']),200000);self.assertTrue(result['content'].endswith('legacy error'))
        outside=Path(self.temp.name)/'outside';outside.write_text('secret');(directory/'reviewer.log').symlink_to(outside)
        with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/runs/RUN-legacy/reviewer')
        self.assertEqual(exc.exception.code,404)
        self.assertIsNone(self.runtime.current)

    def test_browser_log_rate_limit_and_read_requests_do_not_create_noise(self):
        self.runtime.browser_log_times=[__import__('time').monotonic()]*60
        with self.assertRaises(HTTPError) as exc:self.request('/api/v1/debug/logs',{'level':'ERROR','message':'failure','page':'llm'})
        self.assertEqual(exc.exception.code,429)
        before=self.request('/api/v1/debug/logs')['retained']
        for _ in range(3):self.request('/api/v1/debug/logs')
        self.assertEqual(self.request('/api/v1/debug/logs')['retained'],before)
