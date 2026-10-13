"""Crash reporting preserves signals and native traces without timer watchdogs."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
import runpy
import zipfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnostic_support import PythonSnapshots, fatal_diagnostics, termination

class DiagnosticTests(unittest.TestCase):
    def test_signal_and_exit_are_distinct(self):
        self.assertEqual(termination(-11)['signalName'], 'SIGSEGV')
        self.assertEqual(termination(124)['kind'], 'exit')
        self.assertEqual(termination(0)['exitCode'], 0)

    def test_python_snapshots_capture_state_without_native_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            captures = []
            with patch('faulthandler.dump_traceback_later', side_effect=AssertionError('native timer forbidden')):
                with PythonSnapshots(directory, lambda: captures.append(True), interval=.01) as snapshots:
                    snapshots.sample()
            self.assertGreaterEqual(len(captures), 2)
            self.assertIn('test_python_snapshots', (Path(directory) / 'threads.log').read_text())
            self.assertFalse(snapshots.thread.is_alive())

    def test_fatal_handler_retains_real_crash_trace_and_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            script = "from diagnostic_support import fatal_diagnostics; import os,signal,resource; resource.setrlimit(resource.RLIMIT_CORE,(0,0));\\nwith fatal_diagnostics(" + repr(directory) + "): os.kill(os.getpid(),signal.SIGSEGV)"
            env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'scripts')}
            result = subprocess.run([sys.executable, '-c', script.replace('\\n', '\n')], env=env,
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, -signal.SIGSEGV, result.stderr)
            self.assertIn('Fatal Python error', (Path(directory) / 'fatal.log').read_text())
            self.assertIn('sqliteVersion', json.loads((Path(directory) / 'environment.json').read_text()))

    def test_wrapper_preserves_signal_and_creates_support_archive(self):
        root = Path(__file__).resolve().parents[1]
        script = root / 'scripts/check_llm_first_failure.py'
        # Fault injection replaces the child result only; the real reporting
        # and archive paths execute normally and never rerun the failed test.
        process = SimpleNamespace(wait=lambda timeout: -signal.SIGSEGV)
        with (patch('sys.argv', [str(script)]), patch('subprocess.Popen', return_value=process) as spawn,
              patch('builtins.print')):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(script), run_name='__main__')
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(spawn.call_count, 1)
        reports = sorted((root / '.local/test-reports').glob('LLM-CHECK-*/report.json'),
                         key=lambda path: path.stat().st_mtime)
        report_path = reports[-1]
        value = json.loads(report_path.read_text())
        self.assertEqual(value['debug_code'], 'DBG-LLM-CRASH')
        self.assertEqual(value['termination']['signalName'], 'SIGSEGV')
        self.assertEqual(value['exit_code'], -11)
        with zipfile.ZipFile(report_path.parent / 'support.zip') as archive:
            self.assertIn('report.json', archive.namelist())
