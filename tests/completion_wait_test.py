"""Completion evidence and finite execution-policy waits independent of disk polling."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_service import RuntimeService

class CompletionWaitTests(unittest.TestCase):
    def service(self,status='completed'):
        service=RuntimeService.__new__(RuntimeService)
        service.lock=threading.RLock()
        service.current={'id':'run'}
        service.completion_event=Mock()
        service.completion_event.wait.return_value=True
        service.get_run=Mock(return_value={'id':'run','status':status})
        return service
    def test_wait_reads_database_once_after_event_and_has_bounded_budget(self):
        service=self.service()
        result=service.wait_for_terminal('run',70)
        service.completion_event.wait.assert_called_once_with(70)
        service.get_run.assert_called_once_with('run')
        self.assertEqual(result['status'],'completed')
    def test_elapsed_wait_is_a_failure_and_does_not_invent_result(self):
        service=self.service()
        service.completion_event.wait.return_value=False
        with self.assertRaises(TimeoutError):service.wait_for_terminal('run',70)
        service.get_run.assert_not_called()
    def test_notification_requires_actual_persisted_terminal_state(self):
        with self.assertRaises(RuntimeError):self.service('running').wait_for_terminal('run',70)
    def test_cancellation_and_failure_are_terminal_not_success(self):
        for state in ('failed','cancelled','interrupted'):
            self.assertEqual(self.service(state).wait_for_terminal('run',70)['status'],state)
    def test_invalid_or_unbounded_wait_is_rejected(self):
        for value in (True,0,-1,float('inf'),7301,'70'):
            with self.assertRaises(ValueError):self.service().wait_for_terminal('run',value)
