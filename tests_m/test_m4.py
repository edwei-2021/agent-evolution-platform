import os
import pytest
from platform_m.evaluator import command, evaluate, image_id
from platform_m.evidence import Artifacts

GOOD = 'def clamp(value, lower, upper):\n    if lower > upper:\n        raise ValueError("bounds")\n    return max(lower,min(value,upper))\n'

def test_container_command_enforces_digest_and_boundaries():
    cmd = command('sha256:'+'a'*64, 'meval-'+'b'*32)
    for flag in ('--network=none','--read-only','--cap-drop=ALL','--user=65534:65534','--security-opt=no-new-privileges'):
        assert flag in cmd
    assert '--privileged' not in cmd and '--mount' not in cmd
    with pytest.raises(ValueError):
        command('image:latest', 'meval-'+'b'*32)

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
        assert report['verdict'] == expected and report['cleanup']['removed']
        if source == GOOD:
            assert report['results'][0]['passed'] == report['results'][0]['total']
        elif source.startswith('def'):
            assert report['results'][0]['passed'] < report['results'][0]['total']
