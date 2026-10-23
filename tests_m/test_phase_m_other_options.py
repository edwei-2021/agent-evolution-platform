"""Finite option axes for the other supported Skill/model workflow entry points."""
from itertools import product
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from llm_store import LlmStore  # noqa: E402
from repair_store import RepairStore  # noqa: E402
from skill_store import SkillStore  # noqa: E402


def service(root):
    provider = {'revision': 1, 'endpoint': 'http://127.0.0.1:1',
                'config': {'model': 'fixture', 'maxTokens': 1024, 'inferenceTimeout': 3600}}
    return SimpleNamespace(root=root, closed=False,
                           ollama=SimpleNamespace(lock=threading.RLock(), frozen=lambda: provider),
                           logs=SimpleNamespace(append=Mock()))


LLM = list(product(('smoke', 'full'), (None, 10, 3600)))


@pytest.mark.parametrize('profile,timeout', LLM,
                         ids=[f'llm-{profile}-timeout{timeout if timeout is not None else "default"}'
                              for profile, timeout in LLM])
def test_other_workflow_option_matrix_llm(tmp_path, profile, timeout):
    store = object.__new__(LlmStore)
    store.service = service(tmp_path)
    store.snapshot = Mock(return_value={'revision': 1, 'active': {'id': 'LSV-baseline'}})
    options = {'profile': profile, 'maxSeconds': 900, 'expectedRevision': 1, 'providerRevision': 1}
    if timeout is not None:
        options['callTimeoutSeconds'] = timeout
    frozen = store.freeze(options)
    assert frozen['profile'] == profile
    assert frozen['callTimeoutSeconds'] == (timeout or 120)
    assert frozen['callBudget'] > 0


@pytest.mark.parametrize('candidates', (1, 2, 3, 4), ids=[f'skill-candidates{n}' for n in (1, 2, 3, 4)])
def test_other_workflow_option_matrix_skill(tmp_path, candidates):
    store = object.__new__(SkillStore)
    store.service = service(tmp_path)
    store.snapshot = Mock(return_value={'revision': 1, 'active': {'id': 'SKV-baseline'}})
    frozen = store.freeze({'maxCandidates': candidates, 'expectedRevision': 1})
    assert frozen['maxCandidates'] == candidates
    store.service.logs.append.assert_called_once()


REPAIR = list(product((60, 7200), (10, 3600), (2, 12)))


@pytest.mark.parametrize('seconds,timeout,budget', REPAIR,
                         ids=[f'repair-seconds{seconds}-timeout{timeout}-calls{budget}'
                              for seconds, timeout, budget in REPAIR])
def test_other_workflow_option_matrix_repair(tmp_path, monkeypatch, seconds, timeout, budget):
    monkeypatch.setattr('repair_store.sdk_status', lambda root: {'available': True, 'version': 'fixture'})
    store = object.__new__(RepairStore)
    store.service = service(tmp_path)
    frozen = store.freeze({'maxSeconds': seconds, 'callTimeoutSeconds': timeout,
                           'callBudget': budget, 'providerRevision': 1})
    assert (frozen['maxSeconds'], frozen['callTimeoutSeconds'], frozen['callBudget']) == (seconds, timeout, budget)
