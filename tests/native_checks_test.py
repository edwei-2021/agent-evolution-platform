"""Nested health scope, deadlines, failure evidence and subprocess cleanup."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT))
from adaptive_validation import calculate
from native_check_plan import build, validate, MODULES, CHILD_CLEANUP_SECONDS, ROLE_CLEANUP_SECONDS, MODULE_CLEANUP_SECONDS
from native_agents import execute, main
from runtime_service import RuntimeService, ROLES
from platform_m.evidence import archive_failure_evidence
from check_m7_remaining import archive_report
from native_check_support import preserve

CALIBRATION = calculate([0])


class NativeChecksTests(unittest.TestCase):
    def test_explicit_scope_preserves_all_original_modules_and_detects_source_or_budget_drift(self):
        plan = build(ROOT, CALIBRATION)
        self.assertEqual(tuple(r['module'] for r in plan['modules']), MODULES)
        self.assertEqual(set(MODULES), {'sdk_runtime_probe_test.py','setup_orchestrator_test.py',
                                       'setup_test.py','skill_test.py','step_trace_test.py'})
        release_only={'skill_archive_test.py','strata_diagnostic_test.py','strata_workflow_test.py'}
        self.assertEqual(set(MODULES)|release_only,{p.name for p in (ROOT/'tests').glob('s*_test.py')})
        from check_start_selection import release_plan
        release_names={name for name,_ in release_plan(ROOT,sys.executable,'node')}
        self.assertTrue({'python-'+Path(name).stem for name in release_only}<=release_names)
        self.assertEqual(validate(plan, ROOT), plan)
        changed = copy.deepcopy(plan)
        changed['modules'][0]['maximumSeconds'] += 1
        with self.assertRaises(ValueError):
            validate(changed, ROOT)
        changed = copy.deepcopy(plan)
        changed['modules'][0]['sourceHash'] = '0'*64
        with self.assertRaises(ValueError):
            validate(changed, ROOT)

    def test_slow_storage_budget_contains_every_child_and_cleanup_layer(self):
        fast, slow = build(ROOT, CALIBRATION), build(ROOT, calculate([.24]))
        self.assertGreater(slow['maximumSeconds'], fast['maximumSeconds'])
        self.assertGreater(slow['roleMaximumSeconds']['evaluator'],
                           sum(r['maximumSeconds']+CHILD_CLEANUP_SECONDS for r in slow['modules']))
        self.assertGreater(slow['roleMaximumSeconds']['worker'], slow['worker']['maximumSeconds'])
        self.assertGreater(slow['maximumSeconds'], sum(slow['roleMaximumSeconds'].values()))
        self.assertLessEqual(slow['maximumSeconds'], 7200)
        self.assertLess(CHILD_CLEANUP_SECONDS, ROLE_CLEANUP_SECONDS)
        self.assertLess(ROLE_CLEANUP_SECONDS+8, MODULE_CLEANUP_SECONDS)
        from platform_m.gates import CHILD_CLEANUP_SECONDS as outer_cleanup
        self.assertLess(MODULE_CLEANUP_SECONDS, outer_cleanup)
        with self.assertRaises(ValueError):
            build(ROOT, calculate([2]))

    def test_native_parent_uses_frozen_role_limits_instead_of_unrelated_stage_timeout(self):
        def child(role, directory):
            return [sys.executable, '-c', 'import time;time.sleep(.1);print("real child")']
        with tempfile.TemporaryDirectory() as tmp, patch('adaptive_validation.current', return_value=CALIBRATION), \
             patch.object(RuntimeService, 'native_command', staticmethod(child)):
            service = RuntimeService(tmp, stage_timeout=.001)
            try:
                registry = {'agents': [{'id': 'A'+str(i), 'name': r, 'role': r, 'enabled': True} for i, r in enumerate(ROLES)]}
                run = service.start(registry, 'frozen-parent')
                done = service.wait_for_terminal(run['id'], run['nativeCheckPlan']['maximumSeconds']+15)
                self.assertEqual(done['status'], 'completed', done)
            finally:
                service.close()

    def test_child_deadline_terminates_entire_group_and_retains_output(self):
        code = '''import subprocess,sys,signal,json,time
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(300)'])
def stop(signum,frame):
 child.terminate();child.wait();raise SystemExit(143)
signal.signal(signal.SIGTERM,stop)
print(json.dumps({'child':child.pid}),flush=True)
time.sleep(300)
'''
        process = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, start_new_session=True)
        ready = queue.Queue()
        reader = threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            pid = json.loads(ready.get(timeout=120))['child']
            reader.join()
            with tempfile.TemporaryDirectory() as tmp, patch('native_agents.subprocess.Popen', return_value=process):
                output = Path(tmp)/'child.log'
                with redirect_stdout(io.StringIO()):
                    result = execute(['fixture'], ROOT, output, normal=.01, maximum=.1, calibration=CALIBRATION)
                self.assertEqual(result['exitCode'], 124)
                self.assertEqual(result['stopReason'], 'hard_limit')
                self.assertTrue(output.exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def test_native_module_failure_is_failfast_and_keeps_leaf_report(self):
        plan = build(ROOT, CALIBRATION)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory/'native-check-plan.json').write_text(json.dumps(plan))
            def failed(argv, root, output, **kwargs):
                output.write_text('TEST_CASE_RESULT '+json.dumps({'test':'fixture.C.test_failure','status':'failed'})+'\n')
                return {'exitCode': 1, 'output': output.name}
            with patch('native_agents.execute', side_effect=failed) as spawn, redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--role','evaluator','--run-dir',tmp]), 0)
            self.assertEqual(spawn.call_count, 1)
            report = json.loads((directory/'native-check-report.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['activeModule'], MODULES[0])
            self.assertEqual(report['steps'][0]['testCases'][0]['test'], 'fixture.C.test_failure')
            self.assertEqual(json.loads((directory/'evaluator-result.json').read_text())['exitCode'], 1)

    def test_zero_exit_without_complete_case_evidence_cannot_pass(self):
        plan = build(ROOT, CALIBRATION)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory/'native-check-plan.json').write_text(json.dumps(plan))
            def incomplete(argv, root, output, **kwargs):
                output.write_text('no case result records\n')
                return {'exitCode': 0, 'output': output.name}
            with patch('native_agents.execute', side_effect=incomplete) as spawn, redirect_stdout(io.StringIO()):
                main(['--role', 'evaluator', '--run-dir', tmp])
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(json.loads((directory/'evaluator-result.json').read_text())['exitCode'], 1)
            self.assertEqual(json.loads((directory/'native-check-report.json').read_text())['status'], 'failed')

    def test_nested_run_logs_survive_workspace_cleanup_and_redacted_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, reports = Path(tmp)/'runtime', Path(tmp)/'reports'
            from types import SimpleNamespace
            service = SimpleNamespace(local=root/'.local', current={'id':'RUN-fixture','status':'failed'})
            run = service.local/'runs/RUN-fixture'
            run.mkdir(parents=True)
            (run/'native-check-report.json').write_text(json.dumps({'activeModule': MODULES[0], 'api_key':'private-value'}))
            (run/'native-sdk_runtime_probe_test.log').write_text('password=private-value\nleaf diagnostic')
            with patch.dict(os.environ, {'AEP_TEST_REPORT_DIR':str(reports)}), redirect_stdout(io.StringIO()):
                saved = preserve(service, 'runtime_test.RuntimeTests.test_native')
            import shutil
            shutil.rmtree(root)
            self.assertTrue((saved/'native-check-report.json').is_file())
            (reports/'report.json').write_text('{}')
            with zipfile.ZipFile(archive_report(reports)) as archive:
                leaf = next(n for n in archive.namelist() if n.endswith('native-sdk_runtime_probe_test.log'))
                self.assertIn('leaf diagnostic', archive.read(leaf).decode())
                self.assertNotIn('private-value', b''.join(archive.read(n) for n in archive.namelist()).decode())
            escaped = Path(tmp)/'outside.log'
            escaped.write_text('outside must never be exported')
            (saved/'escape.log').symlink_to(escaped)
            with zipfile.ZipFile(Path(tmp)/'gate.zip', 'w') as archive:
                archive_failure_evidence(archive, reports, 'release/')
            with zipfile.ZipFile(Path(tmp)/'gate.zip') as archive:
                self.assertFalse(any(n.endswith('escape.log') for n in archive.namelist()))


if __name__ == '__main__':
    unittest.main()
