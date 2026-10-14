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
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_service import RuntimeService, ROLES, validate_bindings
from serve_gui import GuiHandler, DIST


def registry():
    return {'agents': [{'id': f'AG-{i+1:03}', 'name': role, 'role': role, 'enabled': True} for i, role in enumerate(ROLES)]}


def wait_for(service, identifier, check, timeout=None):
    timeout = timeout if timeout is not None else len(ROLES) * service.stage_timeout + 15
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        run = service.get_run(identifier)
        if check(run):
            return run
        if run['status'] in ('completed', 'failed', 'cancelled', 'interrupted'):
            raise AssertionError('Unexpected terminal state while awaiting runtime condition: ' + str(run))
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
                # This workflow launches nested JS/Python checks. Wait on terminal persistence
                # using the supervisor's bounded per-role execution limits.
                timeout = run['nativeCheckPlan']['maximumSeconds'] + 15
                done = service.wait_for_terminal(run['id'], timeout)
                self.assertEqual(done['status'], 'completed', done)
                self.assertTrue(done['checksPassed'])
                self.assertIn('review.json', done['artifacts'])
                directory = Path(tmp) / '.local/runs' / run['id']
                self.assertEqual(json.loads((directory / 'worker-result.json').read_text())['exitCode'], 0)
                nested = json.loads((directory/'native-check-report.json').read_text())
                self.assertEqual(nested['status'], 'completed')
                self.assertEqual(len(nested['steps']), len(run['nativeCheckPlan']['modules']))
                for row in nested['steps']:
                    self.assertEqual(len(row['testCases']), row['cases'])
                    self.assertTrue(all(c['status'] == 'passed' for c in row['testCases']), row)
                self.assertFalse(json.loads((directory / 'reflection.json').read_text())['skillChanged'])
                self.assertFalse(json.loads((directory / 'review.json').read_text())['published'])
            except BaseException:
                service.close()
                from native_check_support import preserve
                try:
                    preserve(service, self.id())
                except OSError as exc:
                    print('NATIVE_TEST_SUPPORT_ERROR '+str(exc), flush=True)
                raise
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

    def test_cold_discovery_cannot_block_read_routes_or_duplicate_probes(self):
        import sdk_runtime_probe as probes
        release, entered = threading.Event(), threading.Event()
        probes._successful_probe.cache_clear()
        probes._observed.clear()
        def slow_probe(executable, distribution, module, required, symbol=''):
            entered.set()
            if not release.wait(10):
                raise AssertionError('read endpoint waited for optional SDK import')
            return {'available': True, 'version': required, 'python': str(executable),
                    'requiredVersion': required, 'errorCode': None, 'error': None}
        try:
            with patch.object(probes, 'probe', side_effect=slow_probe) as probe:
                caps = self.request('/api/v1/runtime/capabilities')
                self.assertFalse(caps['nanobotInstalled'])
                self.assertTrue(entered.wait(2))
                for path in ('/api/v1/llm/skills', '/api/v1/skills', '/api/v1/runtime',
                             '/api/v1/repair', '/api/v1/gepa', '/api/v1/runtime/capabilities'):
                    self.request(path)  # real HTTP timeout remains five seconds
                self.assertEqual(probe.call_count, 1)
                self.assertFalse(self.runtime.ollama.operation.locked())
                release.set()
                self.runtime.discovery_thread.join(5)
                self.assertFalse(self.runtime.discovery_thread.is_alive())
                live = self.request('/api/v1/runtime')
                self.assertTrue(live['repair']['sdk']['available'])
                self.assertTrue(live['gepa']['optimizer']['available'])
                self.assertEqual(probe.call_count, 2)  # one nanobot and one GEPA probe
                # Replacing the interpreter identity within the same five-minute
                # window must schedule discovery again, not stay pending forever.
                candidate = self.runtime.root/'.venv-nanobot/bin/python'
                candidate.parent.mkdir(parents=True)
                candidate.write_text('fixture interpreter identity')
                self.runtime.sdk_snapshot()
                self.runtime.discovery_thread.join(5)
                self.assertTrue(self.request('/api/v1/runtime')['repair']['sdk']['available'])
                self.assertEqual(probe.call_count, 4)
                self.assertEqual(self.request('/api/v1/llm/skills')['activeVersionId'], 'LSV-baseline')
        finally:
            release.set()
            if self.runtime.discovery_thread:
                self.runtime.discovery_thread.join(5)
            probes._successful_probe.cache_clear()
            probes._observed.clear()

    def test_sdk_submission_preflight_cannot_block_state_reads(self):
        from ollama_bridge import DEFAULTS
        self.runtime.ollama.save({**DEFAULTS, 'host': '127.0.0.1', 'port': 1, 'model': 'not-dispatched'}, 0)
        entered, release = threading.Event(), threading.Event()
        errors = []
        def slow_sdk(root):
            entered.set()
            release.wait(10)
            return {'available': False, 'error': 'fixture SDK failure'}
        def submit():
            try:
                self.runtime.start(registry(), 'cold-submit', 'nanobot-repair', {
                    'maxSeconds': 60, 'callTimeoutSeconds': 10, 'callBudget': 8, 'providerRevision': 1})
            except RuntimeError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=submit)
        try:
            with patch('repair_store.sdk_status', side_effect=slow_sdk):
                thread.start()
                self.assertTrue(entered.wait(2))
                live = self.request('/api/v1/runtime')
                self.assertIsNone(live['latestRun'])
                self.assertFalse(self.runtime.ollama.operation.locked())
                release.set();thread.join(5)
                self.assertEqual(errors, ['fixture SDK failure'])
        finally:
            release.set();thread.join(5)

    def test_gepa_revision_is_rechecked_after_unlocked_sdk_preflight(self):
        def changed(options):
            with self.runtime.connect() as db:
                db.execute('UPDATE gepa_state SET revision=revision+1')
            return {'provider': {'revision': 0}}
        with patch.object(self.runtime.gepa, 'freeze', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'state changed'):
                self.runtime.start(registry(), 'stale-preflight', 'gepa-evolution', {'expectedRevision': 1})
        self.assertIsNone(self.runtime.current)
        self.assertFalse(self.runtime.ollama.operation.locked())

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
