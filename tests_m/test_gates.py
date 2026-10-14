import json
import io
import os
import subprocess
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from platform_m.gates import Gates, execute, normal_budget, plans

def test_acceptance_pytest_disables_nested_capture():
    commands=[command for _,checks in plans(Path('.'),sys.executable)
              for command in checks if len(command)>2 and command[1:3]==['-m','pytest']]
    assert commands
    assert all('-s' in command for command in commands)
    assert all('-vv' in command and '--durations=0' in command for command in commands)

def test_m2_and_m7_python_test_files_are_separate_timed_commands():
    checks=plans(Path('.'),sys.executable)
    m2=next(commands for step,commands in checks if step=='M2')
    m7=next(commands for step,commands in checks if step=='M7')
    assert any('tests_m/test_m2.py' in command for command in m2)
    assert any('tests_m/test_nanobot_bridge.py' in command for command in m2)
    assert not any('tests_m/test_m2.py' in command and 'tests_m/test_nanobot_bridge.py' in command for command in m2)
    assert any('tests_m/test_m7.py' in command for command in m7)
    assert any('tests_m/test_gates.py' in command for command in m7)
    assert not any('tests_m/test_m7.py' in command and 'tests_m/test_gates.py' in command for command in m7)

def test_m1_frontend_gate_uses_the_project_node_runtime():
    root=Path('/project')
    with patch('platform_m.gates.find_node',return_value={'path':'/project/.tools/node/bin/node'}):
        m1=next(checks for step,checks in plans(root,sys.executable) if step=='M1')
    assert m1[1][0]=='/project/.tools/node/bin/node'

def test_command_monitor_streams_output_reports_overrun_and_continues():
    command=[sys.executable,'-u','-c','import time;print("child-start",flush=True);time.sleep(.16);print("child-end",flush=True)']
    terminal=io.StringIO()
    with patch('builtins.input',return_value='y'),redirect_stdout(terminal):
        code,output,timing=execute(command,Path.cwd(),os.environ,timeout=1,normal_seconds=.02,
                                   prompt_after=.05,interval=.01)
    assert code==0 and 'child-start' in output and 'child-end' in output
    assert 'M_CHECK_OVERRUN' in terminal.getvalue()
    assert 'M_CHECK_WAIT_DECISION' in terminal.getvalue()
    assert 'M_CHECK_WAIT_APPROVED' in terminal.getvalue()
    assert timing['extension_approved'] and timing['over_normal_seconds']>=.1

def test_command_monitor_stops_process_when_wait_is_declined():
    command=[sys.executable,'-c','import time;time.sleep(5)']
    with patch('builtins.input',return_value='n'),redirect_stdout(io.StringIO()):
        code,output,timing=execute(command,Path.cwd(),os.environ,timeout=1,normal_seconds=.01,
                                   prompt_after=.02,interval=.01)
    assert code==125 and timing['stopped_by_user']
    assert 'M_CHECK_STOPPED_BY_USER' in output

def test_command_monitor_keeps_a_finite_hard_limit_after_wait_approval():
    command=[sys.executable,'-c','import time;time.sleep(5)']
    with patch('builtins.input',return_value='y'),redirect_stdout(io.StringIO()):
        code,output,timing=execute(command,Path.cwd(),os.environ,timeout=.15,normal_seconds=.02,
                                   prompt_after=.04,interval=.01)
    assert code==124 and timing['extension_approved']
    assert 'M_CHECK_HARD_LIMIT' in output

def test_nested_monitor_does_not_duplicate_overrun_heartbeat():
    command=[sys.executable,'-u','-c','import time;time.sleep(.08)']
    terminal=io.StringIO()
    with redirect_stdout(terminal):
        code,_,_=execute(command,Path.cwd(),os.environ,timeout=1,normal_seconds=.01,
                         prompt_after=2,interval=.01,report_overrun=False)
    assert code==0
    assert 'M_CHECK_OVERRUN' not in terminal.getvalue()

def test_failure_generates_bundle_and_blocks_following_command(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],capture_output=True,check=True)
    (tmp_path/'input.txt').write_text('fixture')
    runner = Gates(tmp_path)
    result = runner.run([
        ('M1', [[sys.executable,'-c','print("first command passed")'],
                [sys.executable,'-c','print("token=private-value");raise SystemExit(3)']]),
        ('M2', [[sys.executable,'-c','raise SystemExit("must never run")']])])
    assert result['status'] == 'blocked'
    assert [r['status'] for r in result['checks']] == ['failed','blocked']
    bundle = json.loads((tmp_path/result['checks'][0]['bundle']).read_text())
    assert 'private-value' not in str(bundle)
    assert bundle['logs'][1]['exit_code'] == 3 and bundle['input_hashes']
    assert result['checks'][0]['command'] == bundle['logs'][1]['command']
    blocked = json.loads((tmp_path/result['checks'][1]['bundle']).read_text())
    assert blocked['logs'][0]['command_executed'] is False
    with zipfile.ZipFile(runner.directory/'support.zip') as archive:
        assert set(archive.namelist()) == {'report.json', 'M1.json', 'M2.json'}
        assert b'private-value' not in archive.read('M1.json')
        assert json.loads(archive.read('report.json'))['status'] == 'blocked'

def test_gate_prints_each_command_estimate_and_persists_runtime(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],capture_output=True,check=True)
    runner=Gates(tmp_path)
    output=io.StringIO()
    command=[sys.executable,'-u','-c','import time;print("visible-child-output",flush=True);time.sleep(.03)']
    with patch('platform_m.gates.normal_budget',return_value=5),redirect_stdout(output):
        result=runner.run([('M1',[command])])
    assert result['checks'][0]['status']=='passed'
    assert 'M_CHECK_EXPECTED step=M1 command=1/1' in output.getvalue()
    assert 'visible-child-output' in output.getvalue()
    row=json.loads((tmp_path/result['checks'][0]['bundle']).read_text())
    assert row['monitor_policy']=='m-command-watch-v1'
    assert row['logs'][0]['elapsed_seconds']>=0

def test_normal_estimate_adapts_from_recent_successful_command(tmp_path):
    folder=tmp_path/'.local/m/support/MCHECK-history'
    folder.mkdir(parents=True)
    (folder/'report.json').write_text('{}')
    (folder/'M1.json').write_text(json.dumps({'monitor_policy':'m-command-watch-v1','status':'passed',
        'logs':[{'command_index':0,'exit_code':0,'elapsed_seconds':12.0}]}))
    assert normal_budget(tmp_path,'M1',0)==18

def test_missing_dependency_is_blocked_with_remediation(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],capture_output=True,check=True)
    result = Gates(tmp_path).run([('M4',[[sys.executable,'-c','raise SystemExit(78)']])], os.environ)
    check = result['checks'][0]
    assert check['status'] == 'blocked' and 'Docker' in check['remediation']
