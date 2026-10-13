"""Tracing reuses runner journals without changing span visibility."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from debug_log import DebugLog
from step_trace import traced

class JournalReuseTests(unittest.TestCase):
    def test_nested_runner_spans_reuse_journal_and_preserve_events(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / '.local/runs/RUN-test'
            directory.mkdir(parents=True)
            logs = DebugLog(root)
            class Runner:
                config = {}
                @traced('llm', 'outer')
                def outer(self):
                    return self.inner()
                @traced('llm', 'inner')
                def inner(self):
                    return 42
            runner = Runner()
            runner.directory = directory
            runner.client = SimpleNamespace(logs=logs)
            with patch('step_trace.context', side_effect=AssertionError('redundant journal initialization')):
                self.assertEqual(runner.outer(), 42)
            rows = logs.list(run_id='RUN-test')['records']
            self.assertEqual(len(rows), 4)
            self.assertEqual([r['details']['event'] for r in reversed(rows)],
                             ['STEP_STARTED', 'STEP_STARTED', 'STEP_COMPLETED', 'STEP_COMPLETED'])

    def test_different_log_root_uses_routed_context(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / '.local/runs/RUN-test'
            logs = DebugLog(root)
            class Runner:
                @traced('llm', 'routed')
                def call(self): return 1
            runner = Runner()
            runner.directory = directory
            runner.config = {'logRoot': str(Path(root) / 'other')}
            runner.client = SimpleNamespace(logs=logs)
            with patch('step_trace.context', return_value=(logs, 'correlated')) as context:
                self.assertEqual(runner.call(), 1)
                context.assert_called_once()
            self.assertEqual(logs.list(run_id='correlated')['matched'], 2)
