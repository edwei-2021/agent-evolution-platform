import os
import subprocess
import pytest
from unittest.mock import patch
from platform_m.evaluator import cleanup_container, command, evaluate, image_id
from platform_m.evidence import Artifacts

GOOD = 'def clamp(value, lower, upper):\n    if lower > upper:\n        raise ValueError("bounds")\n    return max(lower,min(value,upper))\n'

def test_container_command_enforces_digest_and_boundaries():
    cmd = command('sha256:'+'a'*64, 'meval-'+'b'*32)
    for flag in ('--network=none','--read-only','--cap-drop=ALL','--user=65534:65534','--security-opt=no-new-privileges'):
        assert flag in cmd
    assert '--privileged' not in cmd and '--mount' not in cmd
    with pytest.raises(ValueError):
        command('image:latest', 'meval-'+'b'*32)

def test_cleanup_waits_until_docker_confirms_container_absent():
    responses = [
        subprocess.CompletedProcess([], 0, 'meval-test\n', ''),
        subprocess.CompletedProcess([], 0, 'removing\n', ''),
        subprocess.CompletedProcess([], 0, 'meval-test\n', ''),
        subprocess.CompletedProcess([], 1, '', 'Error: No such object: meval-test'),
    ]
    with patch('platform_m.evaluator.subprocess.run', side_effect=responses) as run, \
         patch('platform_m.evaluator.time.sleep'):
        result = cleanup_container('meval-test', timeout=1)
    assert result['removed'] is True
    assert result['last_state'] is None
    assert run.call_count == 4

def test_evaluator_preserves_original_error_when_cleanup_fails():
    job = [{'source':'def clamp(value, lower, upper):\n    return value\n','split':'hidden'}]
    cleanup = {'container':'meval-test','removed':False,'remove_exit_code':1,
               'remove_stderr':'daemon unavailable','inspect_exit_code':1,
               'inspect_stderr':'daemon unavailable','last_state':None}
    with patch('platform_m.evaluator.image_id', return_value='sha256:'+'a'*64), \
         patch('platform_m.evaluator.subprocess.run',
               side_effect=subprocess.TimeoutExpired(['docker','run'], 10)), \
         patch('platform_m.evaluator.cleanup_container', return_value=cleanup):
        report = evaluate(job, 'aep-evaluator:m')
    assert report['verdict'] == 'invalid_evaluation'
    assert report['failure_category'] == 'integrity'
    assert report['evaluation_verdict'] == 'fail'
    assert report['evaluation_failure_category'] == 'timeout'
    assert report['cleanup']['removed'] is False

def test_artifact_integrity_and_traversal(tmp_path):
    artifacts = Artifacts(tmp_path)
    h = artifacts.put({'immutable':True})
    assert artifacts.get(h) == {'immutable': True}
    artifacts.path(h).write_text('tampered')
    with pytest.raises(ValueError):
        artifacts.get(h)
    with pytest.raises(ValueError):
        artifacts.get('../../secret')

def test_real_docker_isolation_good_bad_malicious_and_cleanup():
    if os.environ.get('M_REQUIRE_DOCKER') != '1':
        pytest.skip('Component profile only; M4 acceptance requires M_REQUIRE_DOCKER=1')
    image = image_id(os.environ.get('M_EVALUATOR_IMAGE', 'aep-evaluator:m'))
    for source, expected in [(GOOD,'pass'), ('def clamp(value, lower, upper):\n    return value\n','fail'),
                              ('import os\ndef clamp(value, lower, upper):\n    return os.open("/evaluator/repair_fixture.py",0)\n','fail')]:
        report = evaluate([{'source':source,'split':'hidden'}], image)
        assert report['verdict'] == expected and report['cleanup']['removed'], report
        if source == GOOD:
            assert report['results'][0]['passed'] == report['results'][0]['total']
        elif source.startswith('def'):
            assert report['results'][0]['passed'] < report['results'][0]['total']
