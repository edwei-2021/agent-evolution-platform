"""Bounded setup command failure is preserved, with redacted output."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import io
import unittest
from unittest.mock import patch
from argparse import Namespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('setup_orchestrator',Path(__file__).resolve().parents[1]/'scripts/complete_m_setup.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SetupOrchestratorTests(unittest.TestCase):
    def test_setup_baseline_adapts_to_successful_stage_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report=root/'.local/setup-reports/SETUP-old/report.json'
            report.parent.mkdir(parents=True)
            report.write_text('{"steps":[{"step":"base-environment","status":"passed","started_at":100,"finished_at":120}]}')
            self.assertEqual(module.normal_budget('base-environment',300,root),30)

    def test_exit_code_and_redacted_log_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'test.log'
            code=module.execute([sys.executable,'-c','print("token=private-value");raise SystemExit(3)'],
                                directory,os.environ.copy(),target,10)
            self.assertEqual(code,3)
            self.assertNotIn('private-value',target.read_text())
    def test_secret_url_is_redacted(self):
        self.assertNotIn('private',module.safe('https://user:private@example.com/simple'))
    def test_first_gate_failure_blocks_all_installation_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.venv/bin').mkdir(parents=True)
            (root/'.venv/bin/python').write_text('fixture')
            with (patch.object(module,'ROOT',root),patch.object(module,'execute',return_value=1) as execute,
                  patch('setup_wsl.find_node',return_value=None)):
                self.assertEqual(module.main(Namespace(python=sys.executable,setup_only=False)),1)
            self.assertEqual(execute.call_count,1)
            report=next((root/'.local/setup-reports').glob('*/report.json'))
            import json
            value=json.loads(report.read_text())
            self.assertEqual(value['blocked_by'],'single-llm-gate')
            self.assertEqual(len(value['steps']),1)
    def test_command_deadline_terminates_silent_process(self):
        with tempfile.TemporaryDirectory() as directory:
            code=module.execute([sys.executable,'-c','import time;time.sleep(5)'],directory,
                                os.environ.copy(),Path(directory)/'timeout.log',.05)
            self.assertEqual(code,124)


    def test_long_step_reports_overrun_and_stops_when_user_declines(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'wait.log'
            with patch('sys.stdin',io.StringIO('n\n')),patch('builtins.print') as output:
                code=module.execute([sys.executable,'-c','import time;time.sleep(5)'],directory,
                                    os.environ.copy(),log,2,.01,'slow fixture')
            self.assertEqual(code,125)
            messages=' '.join(str(call.args[0]) for call in output.call_args_list)
            self.assertIn('SETUP_OVERRUN',messages)
            self.assertIn('SETUP_EXPECTED',messages)
            self.assertIn('SETUP_WAIT_DECISION',messages)
            self.assertIn('SETUP_WAIT_DECLINED',messages)

    def test_long_step_continues_reporting_after_user_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'wait.log'
            with patch('sys.stdin',io.StringIO('yes\n')),patch('builtins.print') as output:
                code=module.execute([sys.executable,'-c','import time;time.sleep(.3)'],directory,
                                    os.environ.copy(),log,1,.01,'slow fixture')
            self.assertEqual(code,0)
            messages=' '.join(str(call.args[0]) for call in output.call_args_list)
            self.assertIn('SETUP_WAIT_APPROVED',messages)
            self.assertIn('over_normal_seconds=',messages)

    def test_prompt_is_ten_times_normal_capped_at_thirty_minutes(self):
        self.assertEqual(module.prompt_after_seconds(15),150)
        self.assertEqual(module.prompt_after_seconds(600),1800)
        self.assertEqual(module.prompt_after_seconds(2000),2000)

    def test_calibration_failure_retains_support_and_blocks_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (patch.object(module, 'ROOT', root), patch.object(module, 'execute') as execute,
                  patch('setup_wsl.find_node', return_value=None),
                  patch('adaptive_validation.calibrate', side_effect=OSError('DBG-ADAPT-002: unavailable'))):
                self.assertEqual(module.main(Namespace(python=sys.executable, setup_only=False)), 1)
                execute.assert_not_called()
            import json
            report = json.loads(next((root / '.local/setup-reports').glob('*/report.json')).read_text())
            self.assertEqual(report['blocked_by'], 'adaptive-calibration')
            self.assertIn('DBG-ADAPT-002', report['remediation'])
