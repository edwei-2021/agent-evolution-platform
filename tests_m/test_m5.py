import copy
import pytest
from platform_m.dataset import built_in, compare, import_dataset, feedback
from platform_m.evidence import Artifacts
from tests_m.helpers import evaluations

def test_dataset_linter_and_cross_split_leakage(tmp_path):
    artifacts = Artifacts(tmp_path)
    identifier = built_in(artifacts)
    value = artifacts.get(identifier)
    assert len(value['tasks']) == 50
    value['tasks'][20]['family'] = value['tasks'][0]['family']
    with pytest.raises(ValueError, match='leakage'):
        import_dataset(value, artifacts)

def test_aggregate_gain_cannot_hide_individual_regression(tmp_path):
    artifacts = Artifacts(tmp_path)
    identifier = built_in(artifacts)
    values = evaluations(artifacts, identifier, lose=0)
    report = compare(values, artifacts.get(identifier))
    assert report['totals']['candidate'] > report['totals']['baseline']
    assert report['regressions'] and not report['eligible']

def test_mismatch_infrastructure_and_duplicate_block_comparison(tmp_path):
    artifacts = Artifacts(tmp_path)
    identifier = built_in(artifacts)
    values = evaluations(artifacts, identifier)
    assert compare(values, artifacts.get(identifier))['eligible']
    for mode in ('mismatch','invalid','duplicate','missing'):
        data = copy.deepcopy(values)
        if mode == 'mismatch':
            data[0]['snapshot_hash'] = 'different'
        elif mode == 'invalid':
            data[0].update(verdict='invalid_evaluation', score=None, failure_category='infrastructure')
        elif mode == 'duplicate':
            data.append(data[0])
        else:
            data.pop()
        with pytest.raises(ValueError):
            compare(data, artifacts.get(identifier))

def test_reflection_feedback_is_whitelist_only(tmp_path):
    artifacts = Artifacts(tmp_path)
    identifier = built_in(artifacts)
    task = artifacts.get(identifier)['tasks'][0]
    e = evaluations(artifacts, identifier)[0]
    e.update(task_id=task['id'],split='search')
    safe = feedback(task, e)
    assert set(safe) == {'task_id','score','failure_category'}
    with pytest.raises(ValueError):
        feedback({**task,'split':'validation'}, e)
