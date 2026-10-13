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
            plan=check_steps.stages('release');self.assertEqual(plan[0][0],'all-frontend')
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

    def test_release_python_budgets_are_module_specific_and_adapt_from_history(self):
        estimate=check_steps.normal_budget('release','python-llm_test')
        self.assertGreaterEqual(estimate,30)
        with tempfile.TemporaryDirectory() as root, patch('check_steps.ROOT',Path(root)):
            reports=Path(root)/'.local/test-reports/CHECK-old';reports.mkdir(parents=True)
            (reports/'report.json').write_text(json.dumps({'profile':'release','monitorPolicy':check_steps.MONITOR_POLICY,
                'steps':[{'step':'python-llm_test','status':'completed','durationMs':100000}]}))
            self.assertEqual(check_steps.normal_budget('release','python-llm_test'),150)

    def test_overrun_reports_duration_and_user_decline_stops_process(self):
        with tempfile.TemporaryDirectory() as root:
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
