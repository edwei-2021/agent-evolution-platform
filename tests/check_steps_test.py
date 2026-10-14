"""Staged check plans preserve the release gate and persist failure evidence."""
import json
from pathlib import Path
import sys
import tempfile
import io
import os
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_steps
import run_test_module
from check_steps import supervise

class CheckStepsTests(unittest.TestCase):
    def test_prompt_is_ten_times_normal_capped_at_thirty_minutes(self):
        self.assertEqual(check_steps.prompt_after_seconds(15),150)
        self.assertEqual(check_steps.prompt_after_seconds(600),1800)
        self.assertEqual(check_steps.prompt_after_seconds(2000),2000)
    def test_quick_plan_and_release_sdk_requirement(self):
        with patch('check_steps.find_node',return_value={'path':'node'}),patch('check_steps.sdk_status',return_value={'available':False}):
            steps=check_steps.stages('quick');self.assertEqual([s[0] for s in steps],['installer','setup-control','completion','journal','model-transport','step-trace','batch-evaluator','trace-journal','frontend']);self.assertNotIn('llm_test.py',' '.join(' '.join(step[1]) for step in steps))
            with self.assertRaises(RuntimeError):check_steps.stages('release')
        with patch('check_steps.find_node',return_value={'path':'node'}),patch('check_steps.sdk_status',return_value={'available':True,'python':'sdk-python'}),patch('check_steps.gepa_status',return_value={'available':True}):
            plan=check_steps.stages('release');self.assertEqual([x[0] for x in plan[:2]],['filesystem-calibration','all-frontend'])
            python_steps=[row for row in plan if row[0].startswith('python-')]
            self.assertGreater(len(python_steps),10)
            self.assertEqual(python_steps[0][1][0],'sdk-python')
            self.assertIn('run_test_module.py',python_steps[0][1][1])
            self.assertFalse(any(name=='all-python' for name,_ in plan))

    def test_per_module_runner_reports_each_case_and_actual_duration(self):
        with tempfile.TemporaryDirectory() as root:
            tests_dir=Path(root)/'tests';tests_dir.mkdir()
            (tests_dir/'sample_test.py').write_text('import unittest, time\nclass Sample(unittest.TestCase):\n def test_fast(self): time.sleep(.01)\n')
            result=__import__('subprocess').run([sys.executable,str(Path(check_steps.__file__).with_name('run_test_module.py')),
                'sample_test.py','--tests-dir',str(tests_dir)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            lines=[line.removeprefix('TEST_CASE_RESULT ') for line in result.stdout.splitlines()
                   if line.startswith('TEST_CASE_RESULT ')]
            self.assertEqual(len(lines),1)
            case=json.loads(lines[0])
            self.assertEqual(case['status'],'passed')
            self.assertGreater(case['durationMs'],0)

    def test_per_module_runner_stops_after_first_failure(self):
        with tempfile.TemporaryDirectory() as root:
            tests_dir=Path(root)/'tests';tests_dir.mkdir()
            (tests_dir/'sample_test.py').write_text(
                'import unittest\nclass Sample(unittest.TestCase):\n'
                ' def test_a_error(self): raise RuntimeError("first failure")\n'
                ' def test_b_later(self): raise RuntimeError("should never run")\n')
            result=__import__('subprocess').run(
                [sys.executable,str(Path(check_steps.__file__).with_name('run_test_module.py')),
                 'sample_test.py','--tests-dir',str(tests_dir)],
                capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,1)
            rows=[json.loads(line.removeprefix('TEST_CASE_RESULT ')) for line in result.stdout.splitlines()
                  if line.startswith('TEST_CASE_RESULT ')]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['status'],'error')
            started=[json.loads(line.removeprefix('TEST_CASE_STARTED '))['test']
                     for line in result.stdout.splitlines() if line.startswith('TEST_CASE_STARTED ')]
            self.assertEqual(started,['sample_test.Sample.test_a_error'])
            summary=json.loads(next(line.removeprefix('TEST_MODULE_RESULT ')
                                    for line in result.stdout.splitlines()
                                    if line.startswith('TEST_MODULE_RESULT ')))
            self.assertEqual(summary['testsRun'],1)

    def test_release_python_budgets_are_module_specific_and_adapt_from_history(self):
        estimate=check_steps.normal_budget('release','python-llm_test')
        self.assertGreaterEqual(estimate,30)
        with tempfile.TemporaryDirectory() as root, patch('check_steps.ROOT',Path(root)):
            reports=Path(root)/'.local/test-reports/CHECK-old';reports.mkdir(parents=True)
            (reports/'report.json').write_text(json.dumps({'profile':'release','monitorPolicy':check_steps.MONITOR_POLICY,
                'steps':[{'step':'python-llm_test','status':'completed','durationMs':100000}]}))
            self.assertEqual(check_steps.normal_budget('release','python-llm_test'),150)

    def test_first_release_module_budget_uses_filesystem_calibration_and_case_count(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)):
            reports=Path(root)/'.local/test-reports';reports.mkdir(parents=True)
            (reports/'validation-calibration.json').write_text(json.dumps({'perCallIoAllowanceSeconds':2}))
            (Path(root)/'tests').mkdir()
            (Path(root)/'tests'/'sample_test.py').write_text(
                'def test_one(): pass\ndef test_two(): pass\ndef test_three(): pass\n')
            self.assertEqual(check_steps.normal_budget('release','python-sample_test'),51)

    def test_gepa_module_budget_includes_multiple_full_workflows(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)):
            reports=Path(root)/'.local/test-reports';reports.mkdir(parents=True)
            (reports/'validation-calibration.json').write_text(json.dumps({'perCallIoAllowanceSeconds':2}))
            self.assertGreaterEqual(check_steps.normal_budget('release','python-gepa_test'),1300)

    def test_gepa_cases_show_distinct_workload_estimates(self):
        with tempfile.TemporaryDirectory() as root,patch('run_test_module.ROOT',Path(root)):
            reports=Path(root)/'.local/test-reports';reports.mkdir(parents=True)
            (reports/'validation-calibration.json').write_text(json.dumps({'perCallIoAllowanceSeconds':2}))
            self.assertEqual(run_test_module.expected_case_seconds(
                'gepa_test.GepaWorkflowTests.test_actual_js_client_to_python_api_dispatch_and_result_validation'),290)
            self.assertEqual(run_test_module.expected_case_seconds(
                'gepa_test.GepaWorkflowTests.test_cancel_stops_actual_gepa_sdk_process'),60)

    def test_overrun_reports_duration_and_user_decline_stops_process(self):
        with tempfile.TemporaryDirectory():
            process=__import__('subprocess').Popen([sys.executable,'-c','import time;time.sleep(5)'],start_new_session=True)
            with patch('check_steps.sys.stdin',io.StringIO('n\n')),patch('builtins.print') as output:
                result=supervise(process,'slow-fixture',.01,2,interval=.01)
            self.assertEqual(result['exitCode'],125)
            self.assertTrue(result['stoppedByUser'])
            self.assertFalse(result['extensionApproved'])
            self.assertTrue(any('TEST_WAIT_DECISION' in str(c.args[0]) for c in output.call_args_list))
            with self.assertRaises(ProcessLookupError):os.kill(process.pid,0)

    def test_monitor_reports_each_overrun_and_continues_after_approval(self):
        import subprocess
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.2)'],start_new_session=True)
        with patch('check_steps.sys.stdin',io.StringIO('yes\n')),patch('builtins.print') as output:
            result=supervise(process,'slow-fixture',.01,1,interval=.01)
        self.assertEqual(result['exitCode'],0)
        self.assertTrue(result['extensionApproved'])
        self.assertTrue(any('TEST_WAIT_APPROVED' in str(c.args[0]) for c in output.call_args_list))
        self.assertGreater(result['overNormalSeconds'],0.1)

    def test_child_output_is_streamed_and_saved_as_progress_evidence(self):
        import subprocess
        with tempfile.TemporaryDirectory() as root:
            log=Path(root)/'module.log'
            process=subprocess.Popen([sys.executable,'-u','-c','print("test_module waiting");import time;time.sleep(.08)'],
                                     stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
            with log.open('w') as saved, patch('builtins.print') as output:
                result=supervise(process,'python-module',1,2,output_path=saved,progress_interval=.02)
            self.assertEqual(result['exitCode'],0)
            self.assertIn('test_module waiting',log.read_text())
            self.assertTrue(any('test_module waiting' in str(c.args) for c in output.call_args_list))

    def test_hard_limit_reports_overrun_before_stopping(self):
        import subprocess
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)'],start_new_session=True)
        with patch('builtins.print') as output:
            result=supervise(process,'hard-limit-fixture',.01,.08,interval=.01)
        self.assertEqual(result['exitCode'],124)
        self.assertTrue(any('TEST_HARD_LIMIT' in str(c.args[0]) and 'over_normal_seconds=' in str(c.args[0])
                            for c in output.call_args_list))

    def test_non_interactive_overrun_never_reads_stdin(self):
        import subprocess
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.25)'],start_new_session=True)
        with patch('check_steps._wait_answer',side_effect=AssertionError('stdin must not be read')):
            result=supervise(process,'batch-fixture',.01,1,interactive=False)
        self.assertEqual(result['exitCode'],0)
        self.assertFalse(result['extensionApproved'])

    def test_module_sigterm_preserves_teardown_and_failed_case_evidence(self):
        import signal
        import subprocess
        with tempfile.TemporaryDirectory() as root:
            tests_dir=Path(root)
            (tests_dir/'signal_test.py').write_text(
                'import pathlib,time,unittest\n'
                'class SignalCase(unittest.TestCase):\n'
                ' def test_wait(self):\n'
                '  print("fixture-ready",flush=True)\n'
                '  try: time.sleep(30)\n'
                '  except Exception: self.fail("cancellation swallowed as an ordinary error")\n'
                ' def tearDown(self): pathlib.Path('+repr(str(tests_dir/'cleanup'))+').write_text("closed")\n')
            process=subprocess.Popen([sys.executable,str(Path(check_steps.__file__).with_name('run_test_module.py')),
                'signal_test.py','--tests-dir',str(tests_dir)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
            try:
                # Wait for the handler to be installed and the case to begin.
                while 'fixture-ready' not in process.stdout.readline():
                    if process.poll() is not None:self.fail('signal fixture exited before its test')
                process.send_signal(signal.SIGTERM)
                output=process.communicate(timeout=5)[0]
                self.assertEqual(process.returncode,1,output)
                self.assertEqual((tests_dir/'cleanup').read_text(),'closed')
                case=json.loads(next(line.removeprefix('TEST_CASE_RESULT ') for line in output.splitlines()
                                     if line.startswith('TEST_CASE_RESULT ')))
                self.assertEqual(case['status'],'error')
                self.assertIn('SIGTERM',output)
            finally:
                if process.poll() is None:process.kill();process.wait()

    def test_pending_stdin_keeps_prompt_visible_and_drains_completed_child(self):
        import subprocess
        read_fd,write_fd=os.pipe()
        process=subprocess.Popen([sys.executable,'-u','-c',
            'import time;print("before");time.sleep(.25);print("after")'],
            stdout=subprocess.PIPE,text=True,start_new_session=True)
        try:
            with os.fdopen(read_fd) as source,patch('check_steps.sys.stdin',source),patch('builtins.print') as output:
                result=supervise(process,'pending-input',.01,1)
            self.assertEqual(result['exitCode'],0)
            prompts=[call for call in output.call_args_list if 'TEST_WAIT_DECISION' in str(call.args)]
            self.assertEqual(len(prompts),1)
            self.assertNotEqual(prompts[0].kwargs.get('end'),'')
            self.assertTrue(any('after' in str(call.args) for call in output.call_args_list))
        finally:
            os.close(write_fd)

    def test_pending_stdin_cannot_disable_the_absolute_deadline(self):
        import subprocess
        read_fd,write_fd=os.pipe()
        process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
        try:
            with os.fdopen(read_fd) as source,patch('check_steps.sys.stdin',source):
                result=supervise(process,'bounded-input',.01,.3)
            self.assertEqual(result['exitCode'],124)
            self.assertLess(result['durationMs'],2000)
            self.assertEqual(result['stopReason'],'hard_limit')
            self.assertIsNotNone(process.poll())
        finally:
            os.close(write_fd)

    def test_batch_report_retains_policy_control_frames_and_last_output(self):
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),\
             patch('check_steps.stages',return_value=[('fixture',[sys.executable,'-u','-c','print("last evidence")'])]):
            output=io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(check_steps.run('release',interactive=False,monitor_id='fixture-id'),0)
            control=[json.loads(line.removeprefix('CHECK_MONITOR ')) for line in output.getvalue().splitlines()
                     if line.startswith('CHECK_MONITOR ')]
            self.assertEqual(control[0]['id'],'fixture-id')
            self.assertEqual(control[0]['index'],1)
            report=json.loads(Path(control[0]['report']).read_text())
            self.assertEqual(report['waitPolicy'],'bounded_non_interactive')
            self.assertIsNone(report['steps'][0]['promptAfterSeconds'])
            self.assertIn('last evidence',(Path(control[0]['report']).parent/'fixture.log').read_text())

    def test_partial_case_json_keeps_the_failure_report_and_raw_log(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),\
             patch('check_steps.stages',return_value=[('fixture',[sys.executable,'-c',
                 'print("TEST_CASE_RESULT {broken");raise SystemExit(3)'])]):
            self.assertEqual(check_steps.run('release',interactive=False),1)
            path=next(Path(root).glob('.local/test-reports/*/report.json'))
            row=json.loads(path.read_text())['steps'][0]
            self.assertEqual(row['exitCode'],3)
            self.assertEqual(row['incompleteCaseRecords'],1)
            self.assertIn('{broken',(path.parent/'fixture.log').read_text())

    def test_ctrl_c_is_distinguished_from_declining_the_wait_prompt(self):
        class InterruptedProcess:
            pid=999999
            stdout=None
            returncode=-15
            def poll(self):return None
            def wait(self,timeout=None):
                if not hasattr(self,'interrupted'):
                    self.interrupted=True
                    raise KeyboardInterrupt
                return self.returncode
        process=InterruptedProcess()
        with patch('check_steps.os.killpg'),patch('builtins.print'):
            result=supervise(process,'ctrl-c-fixture',10,20)
        self.assertEqual(result['exitCode'],130)
        self.assertEqual(result['stopReason'],'ctrl_c')

    def test_success_report_has_each_started_and_completed_step(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),patch('check_steps.stages',return_value=[('one',[sys.executable,'-c','print("PASS one")']),('two',[sys.executable,'-c','print("PASS two")'])]):
            self.assertEqual(check_steps.run('quick'),0);path=next(Path(root).glob('.local/test-reports/*/report.json'));data=json.loads(path.read_text())
            self.assertEqual(data['status'],'completed');self.assertEqual(len(data['steps']),2)
            self.assertTrue(all(s['startedAt'] and s['finishedAt'] and s['durationMs']>=0 for s in data['steps']))
            self.assertTrue(all(s['normalSeconds'] and s['promptAfterSeconds'] and s['maximumSeconds'] for s in data['steps']))
            self.assertIn('PASS one',(path.parent/'one.log').read_text())
    def test_failure_stops_next_stage_and_preserves_stdout_and_exit_code(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),patch('check_steps.stages',return_value=[('failed',[sys.executable,'-c','print("FAIL details"); raise SystemExit(3)']),('never',[sys.executable,'-c','print("should not run")'])]):
            self.assertEqual(check_steps.run('release'),1);path=next(Path(root).glob('.local/test-reports/*/report.json'));data=json.loads(path.read_text())
            self.assertEqual(data['status'],'failed');self.assertEqual(len(data['steps']),1);self.assertEqual(data['steps'][0]['exitCode'],3)
            self.assertIn('FAIL details',(path.parent/'failed.log').read_text());self.assertFalse((path.parent/'never.log').exists())

if __name__=='__main__':unittest.main()
