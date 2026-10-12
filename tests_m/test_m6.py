import copy
import sqlite3
import pytest
from platform_m.budget import Budget
from tests_m.helpers import approved_release

def test_signature_permissions_activation_parent_and_rollback(tmp_path):
    service, first, manifest = approved_release(tmp_path)
    with pytest.raises(PermissionError):
        service.activate(first, 0, 'operator', 'operator')
    assert service.activate(first, 0, 'owner', 'approver')['hash'] == first
    frozen = copy.deepcopy(service.artifacts.get(first))
    second_manifest = {**manifest, 'parent_release': first, 'seed': 9}
    second = service.register(second_manifest)
    service.approve(second, 'owner', 'approver', 'next test fixture')
    with pytest.raises(RuntimeError):
        service.activate(second, 0, 'owner', 'approver')
    assert service.activate(second, 1, 'owner', 'approver')['hash'] == second
    assert service.activate(first, 2, 'owner', 'approver', rollback=True)['hash'] == first
    assert service.artifacts.get(first) == frozen

def test_release_artifact_tamper_and_immutable_evidence(tmp_path):
    service, identifier, manifest = approved_release(tmp_path)
    with pytest.raises(sqlite3.IntegrityError), service.store.db() as db:
        db.execute('UPDATE releases SET data=?', ('{}',))
    service.artifacts.path(identifier).write_text('{}')
    with pytest.raises(ValueError):
        service.activate(identifier, 0, 'owner', 'approver')

def test_budget_resume_and_over_budget_rejection():
    ceilings = {'search_tasks':80,'final_tasks':120,'reflections':4,'model_calls':1204,'output_tokens':100000}
    budget = Budget(ceilings)
    assert budget.reserve('t1', {'search_tasks':1,'model_calls':6}, {'skill':'S0'})
    budget.finish('t1', 'a'*64)
    resumed = Budget(ceilings, budget.snapshot())
    assert not resumed.reserve('t1', {'search_tasks':1,'model_calls':6}, {'skill':'S0'})
    assert resumed.consumed['model_calls'] == 6
    with pytest.raises(ValueError):
        resumed.reserve('t1', {'search_tasks':1,'model_calls':6}, {'skill':'S1'})
    with pytest.raises(ValueError):
        resumed.reserve('t2', {'search_tasks':80}, {})
