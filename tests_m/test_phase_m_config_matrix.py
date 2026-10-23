"""Every supported GEPA workload/mode/final-repeat configuration, without model dispatch."""
from itertools import product
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from challenge_bank_test import Service  # noqa: E402
from gepa_dataset import skill  # noqa: E402
from gepa_store import GepaStore  # noqa: E402


COMBINATIONS = list(product((True, False), ('smoke', 'full', 'bank'),
                            ('omitted', 'standard', 'explore'), (None, 1, 2, 3)))


@pytest.mark.parametrize('canonical,profile,mode,repetitions', COMBINATIONS,
    ids=[f'{"canonical" if canonical else "legacy"}-{profile}-{mode}-final{repetitions if repetitions is not None else "default"}'
         for canonical, profile, mode, repetitions in COMBINATIONS])
def test_gepa_configuration_freezes_complete_major_option_matrix(tmp_path, canonical, profile, mode, repetitions):
    service = Service(tmp_path)
    service.closed = False
    service.canonical = object() if canonical else None
    provider = {'revision': 1, 'endpoint': 'http://127.0.0.1:1',
                'config': {'model': 'fixture', 'maxTokens': 1024, 'inferenceTimeout': 120}}
    service.ollama = SimpleNamespace(lock=threading.RLock(), frozen=lambda: provider)
    store = object.__new__(GepaStore)
    store.service = service
    store.snapshot = Mock(return_value={
        'revision': 1, 'active': {'id': 'GSV-baseline', 'skill': skill('baseline')},
        'sdk': {'available': True, 'version': '0.3.5'},
        'optimizer': {'available': True, 'version': '0.1.4'}})
    options = {'profile': profile, 'maxSeconds': 7200, 'callTimeoutSeconds': 120,
               'taskCallBudget': 8, 'metricBudget': 120 if mode == 'explore' else 80,
               'proposalBudget': 16 if mode == 'explore' else 8,
               'providerRevision': 1, 'expectedRevision': 1,
               }
    if repetitions is not None:
        options['finalRepetitions'] = repetitions
    if profile == 'bank':
        options['bankRevision'] = 1
    if mode != 'omitted':
        options['searchMode'] = mode
    if not canonical and repetitions is not None:
        with pytest.raises(ValueError, match='canonical ledger'):
            store.freeze(options)
        store.snapshot.assert_not_called()
        return
    frozen = store.freeze(options)
    assert frozen.get('searchMode', 'standard') == ('standard' if mode == 'omitted' else mode)
    assert frozen.get('finalRepetitions', 1) == (repetitions or 1)
    assert bool(frozen.get('explorationPolicy')) == (mode == 'explore')
    assert bool(frozen.get('searchSeed') is not None) == (mode == 'explore')
    assert frozen['comparisonPolicy'] == frozen['provenance']['comparisonPolicy']
    assert frozen['counts'] == ({'train': 20, 'validation': 10, 'heldout': 20} if profile == 'full'
                                else {'train': 4, 'validation': 2, 'heldout': 4} if profile == 'smoke'
                                else {key: len(rows) for key, rows in frozen['datasetSnapshot']['data'].items()})
    expected_final = 2 * (frozen['counts']['validation'] + (repetitions or 1) * frozen['counts']['heldout'])
    assert frozen['callBudget'] == (options['metricBudget'] + expected_final) * options['taskCallBudget'] + options['proposalBudget']


def test_three_final_repetitions_require_canonical_ledger(tmp_path):
    service = Service(tmp_path)
    service.canonical = None
    store = object.__new__(GepaStore)
    store.service = service
    store.snapshot = Mock(side_effect=AssertionError('No SDK/model inspection'))
    with pytest.raises(ValueError, match='canonical ledger'):
        store.freeze({'profile': 'smoke', 'finalRepetitions': 3})
    store.snapshot.assert_not_called()
