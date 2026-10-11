"""Actual subprocess and loopback HTTP tests; no model keys or third-party packages."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_service import RuntimeService, ROLES, validate_bindings
from serve_gui import GuiHandler, DIST


def registry():
    return {'agents': [{'id': f'AG-{i+1:03}', 'name': role, 'role': role, 'enabled': True} for i, role in enumerate(ROLES)]}


def wait_for(service, identifier, check, timeout=15):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        run = service.get_run(identifier)
        if check(run):
            return run
        time.sleep(0.02)
    raise AssertionError('Runtime state did not reach expected condition')


def command(code):
    return lambda role, directory: [sys.executable, '-c', code]


class RuntimeTests(unittest.TestCase):
    def test_real_processes_record_pids_logs_exit_codes_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp, command_factory=command("print('actual tool output')"))
            try:
                run = service.start(registry(), 'request-1')
                done = wait_for(service, run['id'], lambda r: r['status'] == 'completed')
                self.assertEqual(len({a['pid'] for a in done['agents']}), 5)
                self.assertTrue(all(a['exitCode'] == 0 and not a['processAlive'] and a['startedAt'] and a['endedAt'] for a in done['agents']))
                self.assertIn('actual tool output', done['agents'][0]['logTail'])
                self.assertEqual(service.start(registry(), 'request-1')['id'], done['id'])
            finally:
                service.close()
            again = RuntimeService(tmp, command_factory=command('print(1)'))
            try:
                self.assertEqual(again.snapshot()['latestRun']['id'], run['id'])
            finally:
                again.close()

    def test_failure_skips_downstream_and_exposes_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp, command_factory=command('raise SystemExit(7)'))
            try:
                run = service.start(registry(), 'request-fail')
                done = wait_for(service, run['id'], lambda r: r['status'] == 'failed')
                self.assertEqual(done['agents'][0]['exitCode'], 7)
                self.assertTrue(all(a['status'] == 'skipped' for a in done['agents'][1:]))
            finally:
                service.close()

    def test_cancel_terminates_actual_process_and_rejects_concurrent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp, command_factory=command('import time;time.sleep(60)'))
            try:
                run = service.start(registry(), 'request-cancel')
                active = wait_for(service, run['id'], lambda r: r['agents'][0]['processAlive'])
                with self.assertRaises(RuntimeError):
                    service.start(registry(), 'request-second')
                service.cancel(run['id'])
                done = wait_for(service, run['id'], lambda r: r['status'] == 'cancelled')
                self.assertTrue(all(a['status'] == 'cancelled' for a in done['agents']))
                with self.assertRaises(ProcessLookupError):
                    os.kill(active['agents'][0]['pid'], 0)
            finally:
                service.close()

    def test_timeout_stops_process_and_releases_the_run_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp, command_factory=command('import time;time.sleep(60)'), stage_timeout=0.1)
            try:
                run = service.start(registry(), 'request-timeout')
                done = wait_for(service, run['id'], lambda r: r['status'] == 'failed')
                self.assertEqual(done['agents'][0]['error'], 'Stage timed out')
                self.assertFalse(done['agents'][0]['processAlive'])
            finally:
                service.close()

    def test_one_supervisor_per_checkout_and_restart_marks_stale_work_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp, command_factory=command('print(1)'))
            try:
                with self.assertRaises(RuntimeError):
                    RuntimeService(tmp)
                run = service.start(registry(), 'request-restart')
                done = wait_for(service, run['id'], lambda r: r['status'] == 'completed')
                done['status'] = 'running';done['agents'][0]['status'] = 'running';done['agents'][0]['processAlive'] = True
                with service.connect() as db:
                    db.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(done), run['id']))
            finally:
                service.close()
            again = RuntimeService(tmp)
            try:
                recovered = again.get_run(run['id'])
                self.assertEqual(recovered['status'], 'interrupted')
                self.assertIsNone(recovered['agents'][0]['processAlive'])
            finally:
                again.close()

    def test_binding_validation_requires_one_enabled_agent_per_role(self):
        self.assertEqual(len(validate_bindings(registry())), 5)
        for change in [lambda r: r['agents'].pop(), lambda r: r['agents'][0].update(enabled=False), lambda r: r['agents'][0].update(id='../escape'), lambda r: r['agents'][0].update(enabled='true'), lambda r: r['agents'][0].update(role='worker')]:
            r = registry();change(r)
            with self.assertRaises(ValueError):
                validate_bindings(r)

    def test_fixed_native_workflow_executes_actual_project_checks_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeService(tmp)
            try:
                run = service.start(registry(), 'request-native')
                done = wait_for(service, run['id'], lambda r: r['status'] in ('completed', 'failed'), timeout=30)
                self.assertEqual(done['status'], 'completed', done)
                self.assertTrue(done['checksPassed'])
                self.assertIn('review.json', done['artifacts'])
                directory = Path(tmp) / '.local/runs' / run['id']
                self.assertEqual(json.loads((directory / 'worker-result.json').read_text())['exitCode'], 0)
                self.assertFalse(json.loads((directory / 'reflection.json').read_text())['skillChanged'])
                self.assertFalse(json.loads((directory / 'review.json').read_text())['published'])
            finally:
                service.close()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = RuntimeService(self.temp.name, command_factory=command("print('API test')"))
        class Quiet(GuiHandler):
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
        self.server.runtime = self.runtime
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.runtime.close();self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        merged = {'Content-Type': 'application/json', **(headers or {})}
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=merged)
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_poll_start_and_artifact_routes_use_actual_server_snapshots(self):
        caps = self.request('/api/v1/runtime/capabilities')
        self.assertFalse(caps['modelConnected'])
        self.assertIsNone(self.request('/api/v1/runtime')['latestRun'])
        run = self.request('/api/v1/runtime/runs', {'registry': registry(), 'requestId': 'api-run'}, {'X-Lab-Token': caps['csrfToken'], 'Origin': self.base})
        wait_for(self.runtime, run['id'], lambda r: r['status'] == 'completed')
        live = self.request('/api/v1/runtime')
        self.assertEqual(live['latestRun']['id'], run['id'])
        artifact = self.request(f"/api/v1/runtime/runs/{run['id']}/artifacts/coordinator.log")
        self.assertIn('API test', artifact['content'])
        for path in [f"/api/v1/runtime/runs/{run['id']}/artifacts/config.env", '/api/v1/runtime/runs/RUN-absent']:
            with self.assertRaises(HTTPError) as exc:
                self.request(path)
            self.assertEqual(exc.exception.code, 404)

    def test_mutations_require_token_and_reject_cross_origin_and_bad_bindings(self):
        body = {'registry': registry(), 'requestId': 'api-invalid'}
        for headers in [{}, {'X-Lab-Token': self.runtime.csrf_token, 'Origin': 'https://unrelated.example'}, {'X-Lab-Token': self.runtime.csrf_token, 'Sec-Fetch-Site': 'cross-site'}]:
            with self.assertRaises(HTTPError) as exc:
                self.request('/api/v1/runtime/runs', body, headers)
            self.assertEqual(exc.exception.code, 403)
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/v1/runtime/runs', {'registry': {}, 'requestId': 'bad'}, {'X-Lab-Token': self.runtime.csrf_token})
        self.assertEqual(exc.exception.code, 400)
        self.assertIsNone(self.runtime.snapshot()['latestRun'])

    def test_api_rejects_rebinding_host_and_unknown_routes(self):
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/v1/runtime', headers={'Host': 'unrelated.example:8765'})
        self.assertEqual(exc.exception.code, 403)
        with self.assertRaises(HTTPError) as exc:
            self.request('/api/v1/runtime/missing')
        self.assertEqual(exc.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
