import copy
import sqlite3
import pytest
from platform_m.budget import Budget
from tests_m.helpers import approved_release

def test_signature_permissions_activation_parent_and_rollback(posix_tmp_path):
    service, first, manifest = approved_release(posix_tmp_path)
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

def test_release_artifact_tamper_and_immutable_evidence(posix_tmp_path):
    service, identifier, manifest = approved_release(posix_tmp_path)
    with pytest.raises(sqlite3.IntegrityError), service.store.db() as db:
        db.execute('UPDATE releases SET data=?', ('{}',))
    service.artifacts.path(identifier).write_text('{}')
    with pytest.raises(ValueError):
        service.activate(identifier, 0, 'owner', 'approver')

def test_signing_key_uses_linux_state_path_unless_configured_or_legacy(monkeypatch, tmp_path):
    import hashlib
    from platform_m.releases import signing_key_path
    root = tmp_path/'checkout'
    root.mkdir()
    state = tmp_path/'state'
    monkeypatch.setenv('XDG_STATE_HOME', str(state))
    monkeypatch.delenv('AEP_SIGNING_KEY_PATH', raising=False)
    project_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    assert signing_key_path(root) == state/'agent-evolution-platform'/project_id/'signing.key'
    configured = tmp_path/'private'/'signing.key'
    monkeypatch.setenv('AEP_SIGNING_KEY_PATH', str(configured))
    assert signing_key_path(root) == configured.resolve()
    monkeypatch.delenv('AEP_SIGNING_KEY_PATH')
    legacy = root/'.local/m/signing.key'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'legacy key placeholder')
    assert signing_key_path(root) == legacy

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

def test_validation_net_gain_cannot_hide_a_lost_baseline_success(posix_tmp_path):
    service,_,manifest=approved_release(posix_tmp_path)
    with service.store.db() as db:
        import json
        rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM evaluations')]
    first=next(v['task_id'] for v in rows if v['split']=='validation')
    replaced={}
    for value in rows:
        if value['split']=='validation' and value['task_id']==first:
            score=int(value['label']=='baseline')
            new={**value,'id':value['id']+'-regression','score':score,
                 'verdict':'pass' if score else 'fail','failure_category':'none' if score else 'assertion'}
            service.store.evaluation(new);replaced[value['id']]=new['id']
    manifest={**manifest,'result_ids':[replaced.get(i,i) for i in manifest['result_ids']]}
    with pytest.raises(ValueError,match='lost baseline successes'):
        service.register(manifest)

def test_release_replay_rejects_uncommitted_execution_before_evaluator_dispatch(posix_tmp_path):
    from unittest.mock import patch
    service,_,manifest=approved_release(posix_tmp_path)
    task=next(t for t in service.artifacts.get(manifest['dataset_hash'])['tasks'] if t['split']=='validation')
    identifier=service.store.submit('uncommitted-release',{})
    execution={'status':'succeeded','task_id':task['id'],'run_id':identifier,
               'loaded_skill_hash':manifest['skill_hash'],'output':{'candidate_source':'pass'}}
    value={'task_id':task['id'],'split':task['split'],'run_id':identifier,
           'artifacts':[service.artifacts.put(execution),service.artifacts.put({'verdict':'pass'})]}
    with patch('platform_m.evaluator.evaluate',side_effect=AssertionError('No replay before commitment')) as evaluator:
        with pytest.raises(ValueError,match='Committed completed execution'):
            service.replay(value,manifest)
        evaluator.assert_not_called()
