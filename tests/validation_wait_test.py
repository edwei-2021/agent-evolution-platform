"""First-request timing remains bounded and reports terminal failures."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validation_wait import first_request, startup_budget


class FakeService:
    def __init__(self,status='running'):
        self.status=status
    def get_run(self,identifier):
        return {'status':self.status,'error':'fixture failed',
                'agents':[{'role':'worker','status':'running'}],
                'gepaProgress':{'phase':'search','activeRollout':'R0001'}}


class WaitTests(unittest.TestCase):
    def test_startup_budget_scales_but_remains_bounded(self):
        self.assertEqual(startup_budget(0,100),30)
        self.assertEqual(startup_budget(2,100),80)
        self.assertEqual(startup_budget(100,500),180)
        with self.assertRaises(ValueError):startup_budget(-1,100)

    def test_delayed_request_reports_current_role_before_arrival(self):
        event=threading.Event();timer=threading.Timer(.06,event.set)
        output=io.StringIO();timer.start()
        try:
            with redirect_stdout(output):first_request(event,FakeService(),'R',.5,label='delayed',interval=.02)
        finally:timer.join()
        self.assertIn('role=worker',output.getvalue())
        self.assertIn('TEST_REQUEST_RECEIVED',output.getvalue())

    def test_failure_and_timeout_are_actionable(self):
        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(AssertionError,'fixture failed'):
                first_request(threading.Event(),FakeService('failed'),'R',.02,label='terminal',interval=.01)
            with self.assertRaisesRegex(AssertionError,'not observed'):
                first_request(threading.Event(),FakeService(),'R',.02,label='timeout',interval=.01)
