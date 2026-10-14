"""Heartbeat producer/consumer contracts with nonzero clocks and real children."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from scripts import check_steps
from platform_m.gates import execute


def test_default_producer_cadence_fits_parent_silence_allowance():
    from platform_m.gates import CHILD_HEARTBEAT_SECONDS
    assert 0 < check_steps.PROGRESS_INTERVAL_SECONDS < CHILD_HEARTBEAT_SECONDS / 2


@pytest.mark.parametrize('interrupted', [False, True])
def test_llm_failed_teardown_preserves_closed_run_before_cleanup_and_redacted_export(tmp_path, monkeypatch, interrupted):
    monkeypatch.syspath_prepend(str(ROOT/'tests'))
    from llm_test import LlmWorkflowTests, MockModel
    from check_m7_remaining import archive_report
    from run_test_module import ModuleInterrupted
    local = tmp_path/'workspace'
    run = local/'runs'/'RUN-fixture'
    run.mkdir(parents=True)
    (run/'llm-progress.json').write_text(json.dumps({'calls': 7, 'apiKey': 'fixture-sensitive'}))
    (run/'worker.log').write_text('password=fixture-sensitive\n')
    (run/'linked.log').symlink_to(run/'worker.log')
    report = tmp_path/'report'
    monkeypatch.setenv('AEP_TEST_REPORT_DIR', str(report))
    def close():
        service.current['status'] = 'failed'
        (run/'cleanup.log').write_text('worker reaped; slot released')
    service = SimpleNamespace(local=local, current={'id': 'RUN-fixture'}, close=close)
    def cleanup():
        import shutil
        shutil.rmtree(local)
    class Failure(LlmWorkflowTests):
        def setUp(self):
            self.service = service
            self.temp = SimpleNamespace(cleanup=cleanup)
            self.model = SimpleNamespace(shutdown=lambda:None, server_close=lambda:None)
            self.thread = SimpleNamespace(join=lambda:None)
        def runTest(self):
            if interrupted:
                raise ModuleInterrupted('fixture cancellation')
            self.fail('fixture assertion failure')
        def id(self):
            return 'llm_test.Failure.runTest'
    monkeypatch.setattr(MockModel, 'block', None)
    monkeypatch.setattr(MockModel, 'stream_block', None)
    result = unittest.TestResult()
    Failure().run(result)
    assert len(result.failures) + len(result.errors) == 1
    assert not local.exists()
    with zipfile.ZipFile(archive_report(report)) as bundle:
        names = bundle.namelist()
        diagnostic = next(n for n in names if n.endswith('/diagnostic.json'))
        assert '/llm_test/' in diagnostic
        assert json.loads(bundle.read(diagnostic))['run']['status'] == 'failed'
        assert any(n.endswith('/cleanup.log') for n in names)
        assert any(n.endswith('/llm-progress.json') for n in names)
        assert not any(n.endswith('/linked.log') for n in names)
        assert all(b'fixture-sensitive' not in bundle.read(n) for n in names)


@pytest.mark.parametrize('origin', [0.0, 2000.0, 1000000.0])
def test_quiet_under_estimate_emits_heartbeat_independent_of_clock_origin(origin):
    clock = [origin]
    class Child:
        stdout = None
        @property
        def returncode(self):
            return self.poll()
        def poll(self):
            return 0 if clock[0]-origin >= 95 else None
        def wait(self, timeout):
            clock[0] += timeout
            if self.poll() is None:
                raise subprocess.TimeoutExpired('virtual-child', timeout)
            return 0
    output = io.StringIO()
    with patch.object(check_steps, 'time', SimpleNamespace(monotonic=lambda:clock[0])), redirect_stdout(output):
        result = check_steps.supervise(Child(), 'quiet-case', normal=1000, maximum=200,
                                      progress_interval=30, interactive=False)
    heartbeats = [line for line in output.getvalue().splitlines() if line.startswith('TEST_PROGRESS ')]
    assert len(heartbeats) == 3
    assert all('over_normal_seconds=0' in line for line in heartbeats)
    assert 'TEST_OVERRUN ' not in output.getvalue()
    assert result['exitCode'] == 0


def test_real_quiet_child_survives_parent_heartbeat_while_under_normal_estimate():
    code = f'''import json,subprocess,sys
sys.path.insert(0,{str(ROOT/'scripts')!r})
from check_steps import supervise
print('CHECK_MONITOR '+json.dumps({{'id':'heartbeat-contract','index':1,'step':'quiet-case','maximumSeconds':10}}),flush=True)
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3.2)'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
result=supervise(child,'quiet-case',normal=20,maximum=10,progress_interval=.2,interactive=False)
raise SystemExit(result['exitCode'])
'''
    with redirect_stdout(io.StringIO()):
        code,output,timing = execute([sys.executable,'-u','-c',code],ROOT,os.environ,
            timeout=10,interactive=False,report_overrun=False,
            child_monitor={'id':'heartbeat-contract','steps':1},heartbeat_seconds=1)
    assert code == 0, output
    assert output.count('TEST_PROGRESS ') >= 3
    assert 'TEST_OVERRUN ' not in output
    assert timing['elapsed_seconds'] > 3


def test_pre_frame_startup_uses_startup_limit_then_enforces_heartbeat():
    code = '''import json,time
time.sleep(.6)
print('CHECK_MONITOR '+json.dumps({'id':'startup-contract','index':1,'step':'silent','maximumSeconds':20}),flush=True)
time.sleep(10)
'''
    with patch('platform_m.gates.CHILD_CLEANUP_SECONDS',.1),redirect_stdout(io.StringIO()):
        code,output,timing = execute([sys.executable,'-u','-c',code],ROOT,os.environ,
            timeout=5,interactive=False,report_overrun=False,
            child_monitor={'id':'startup-contract','steps':1},heartbeat_seconds=.2)
    assert code == 124
    assert timing['child_step'] == 'silent'
    assert timing['stop_reason'] == 'child_output_stalled'
    assert timing['elapsed_seconds'] >= .6


def test_heartbeats_never_renew_the_authenticated_step_hard_limit():
    code = '''import json,time
print('CHECK_MONITOR '+json.dumps({'id':'bounded-heartbeat','index':1,'step':'stuck','maximumSeconds':.4}),flush=True)
while True:
 print('TEST_PROGRESS supervisor_alive=true',flush=True)
 time.sleep(.03)
'''
    with patch('platform_m.gates.CHILD_CLEANUP_SECONDS',.1),redirect_stdout(io.StringIO()):
        code,output,timing = execute([sys.executable,'-u','-c',code],ROOT,os.environ,
            timeout=5,interactive=False,report_overrun=False,
            child_monitor={'id':'bounded-heartbeat','steps':1},heartbeat_seconds=2)
    assert code == 124
    assert timing['stop_reason'] == 'hard_limit'
    assert timing['elapsed_seconds'] < 5
