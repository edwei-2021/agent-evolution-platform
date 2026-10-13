import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from platform_m.gates import Gates, plans

def test_acceptance_pytest_disables_nested_capture():
    commands=[command for _,checks in plans(Path('.'),sys.executable)
              for command in checks if len(command)>2 and command[1:3]==['-m','pytest']]
    assert commands
    assert all('-s' in command for command in commands)

def test_node_resolver_imports_from_repository_scripts():
    from platform_m.gates import find_node
    result = find_node(Path(__file__).resolve().parents[1])
    assert result is None or isinstance(result, dict)

def test_m1_frontend_gate_uses_the_project_node_runtime():
    root=Path('/project')
    with patch('platform_m.gates.find_node',return_value={'path':'/project/.tools/node/bin/node'}):
        m1=next(checks for step,checks in plans(root,sys.executable) if step=='M1')
    assert m1[1][0]=='/project/.tools/node/bin/node'

def test_failure_generates_bundle_and_blocks_following_command(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],capture_output=True,check=True)
    (tmp_path/'input.txt').write_text('fixture')
    runner = Gates(tmp_path)
    result = runner.run([
        ('M1', [[sys.executable,'-c','print("token=private-value");raise SystemExit(3)']]),
        ('M2', [[sys.executable,'-c','raise SystemExit("must never run")']])])
    assert result['status'] == 'blocked'
    assert [r['status'] for r in result['checks']] == ['failed','blocked']
    bundle = json.loads((tmp_path/result['checks'][0]['bundle']).read_text())
    assert 'private-value' not in str(bundle)
    assert bundle['logs'][0]['exit_code'] == 3 and bundle['input_hashes']
    blocked = json.loads((tmp_path/result['checks'][1]['bundle']).read_text())
    assert blocked['logs'][0]['command_executed'] is False

def test_missing_dependency_is_blocked_with_remediation(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],capture_output=True,check=True)
    result = Gates(tmp_path).run([('M4',[[sys.executable,'-c','raise SystemExit(78)']])], os.environ)
    check = result['checks'][0]
    assert check['status'] == 'blocked' and 'Docker' in check['remediation']
