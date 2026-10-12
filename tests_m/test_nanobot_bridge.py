"""Actual SDK subprocess over loopback model; container enforcement has its own M4 gate."""
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import time
import pytest
from platform_m.adapters import NanobotAdapter
from platform_m.evidence import Artifacts, digest
from platform_m.contracts import Task
from scripts.repair_engine import provenance
from scripts.repair_fixture import SKILL, BASELINE, VISIBLE, HIDDEN, PROMPT
from scripts.ollama_bridge import DEFAULTS
from scripts.repair_runtime import sdk_status

ROOT = Path(__file__).resolve().parents[1]

def test_real_nanobot_adapter_loads_skill_and_returns_execution_facts(tmp_path):
    sdk = sdk_status(ROOT)
    if not sdk['available']:
        pytest.fail('Pinned real SDK required; install scripts/install-nanobot.sh before M2 gate')
    spec = importlib.util.spec_from_file_location('loopback_repair', ROOT/'tests/repair_test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.Model
    model.calls, model.mode, model.gate = [], 'good', None
    server = ThreadingHTTPServer(('127.0.0.1',0),model)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        fixture = {'baseline':BASELINE,'prompt':PROMPT,'visible':VISIBLE,'hidden':HIDDEN}
        config = {'engine':'nanobot-python-repair-v1','taskId':'canonical-clamp','fixture':fixture,
            'skill':SKILL,'sdk':sdk,'provider':{'endpoint':f'http://127.0.0.1:{server.server_port}',
                'config':{**DEFAULTS,'model':'mock-canonical','inferenceTimeout':10,'maxTokens':512}},
            'maxSeconds':60,'deadlineEpoch':time.time()+60,'callBudget':6,'callTimeoutSeconds':10,
            'toolBudget':24,'provenance':provenance(),'logRoot':str(tmp_path)}
        task = Task(id='canonical-clamp',family='clamp',split='search',fixture_hash=digest(fixture),requirement=PROMPT)
        result = NanobotAdapter().run(task.model_dump(),{'skill_hash':digest(SKILL)}, {},'canonical-run',
            Artifacts(tmp_path/'artifacts'),ROOT,tmp_path/'run',config)
        assert result.status == 'succeeded', result.output
        assert result.loaded_skill_hash == digest(SKILL)
        assert result.output['calls'] == 4
        assert result.output['stop_reason'] == 'completed'
        assert result.output['candidate_source'] == module.GOOD
        assert 'score' not in result.model_dump()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
