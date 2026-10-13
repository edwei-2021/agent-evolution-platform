"""Bounded setup command failure is preserved, with redacted output."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('setup_orchestrator',Path(__file__).resolve().parents[1]/'scripts/complete_m_setup.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SetupOrchestratorTests(unittest.TestCase):
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
