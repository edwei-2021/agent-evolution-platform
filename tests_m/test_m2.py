import pytest
from platform_m.adapters import MockAdapter
from platform_m.contracts import RunResult, Task, Evaluation
from platform_m.evidence import Artifacts

TASK = Task(id='unit-task', family='unit-family', split='search', fixture_hash='a'*64, requirement='Repair').model_dump()

@pytest.mark.parametrize('mode', ['succeeded','failed','timed_out','cancelled','infrastructure_error'])
def test_adapter_contract_and_loaded_skill(tmp_path, mode):
    result = MockAdapter().run(TASK, {'skill_hash': 'b'*64}, {'mock_mode': mode}, 'run', Artifacts(tmp_path))
    assert RunResult.model_validate(result.model_dump()).status == mode
    assert result.loaded_skill_hash == 'b'*64
    assert result.artifacts and result.output['mock']

def test_malformed_mock_output_and_unknown_contract_fields_rejected(tmp_path):
    with pytest.raises(ValueError):
        MockAdapter().run(TASK, {'skill_hash': 'b'*64}, {'mock_mode': 'invented'}, 'run', Artifacts(tmp_path))
    with pytest.raises(ValueError):
        Task.model_validate({**TASK, 'extra_tool': 'shell'})

def test_invalid_evaluation_cannot_receive_success_score():
    with pytest.raises(ValueError):
        Evaluation(id='e',run_id='r',task_id='t',repetition=0,label='candidate',split='search',
            verdict='invalid_evaluation',evaluator_hash='a',dataset_hash='b',snapshot_hash='c',
            artifacts=['x'],failure_category='infrastructure',score=1)
