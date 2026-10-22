import copy
import json
import sqlite3
import subprocess
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from platform_m.api import create_app
from platform_m.budget import Budget
from platform_m.release_git import ReleaseGit, REF
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


def test_git_release_publication_reconciles_crash_window_without_duplicate_activation(posix_tmp_path):
    root=posix_tmp_path
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    service,first,manifest=approved_release(root/'.local/m')
    service.git=ReleaseGit(root)
    assert service.activate(first,0,'owner','approver')=={'hash':first,'revision':1}
    assert service.git_status()['synchronized']
    second=service.register({**manifest,'parent_release':first,'seed':19})
    service.approve(second,'owner','approver','new release')
    with patch.object(service.git,'publish',side_effect=RuntimeError('controlled local Git failure')):
        with pytest.raises(RuntimeError,match='controlled local Git failure'):
            service.activate(second,1,'owner','approver')
    assert service.active()=={'hash':second,'revision':2}
    assert service.git_status()['git_hash']==first
    assert service.git_status()['synchronized'] is False
    assert [e['type'] for e in service.store.events(second)].count('activated')==1
    assert [e['type'] for e in service.store.events(second)].count('release.git.pending')==1
    with TestClient(create_app(root,'release-unit',role='approver')) as client:
        headers={'Authorization':'Bearer release-unit'}
        assert client.get('/api/m/releases/git',headers=headers).json()['synchronized'] is True
        assert client.post('/api/m/releases/reconcile',headers=headers,
                           json={'expected_revision':1}).status_code==409
        assert client.post('/api/m/releases/reconcile',headers=headers,
                           json={'expected_revision':2}).json()['synchronized'] is True
    assert service.git_status()['git_hash']==second
    assert [e['type'] for e in service.store.events(second)].count('activated')==1
    assert [e['type'] for e in service.store.events(second)].count('release.git.published')==1
    assert service.activate(first,2,'owner','approver',rollback=True)=={'hash':first,'revision':3}
    assert service.git_status()['git_hash']==first
    logs=(root/'.local/diagnostics/workflows.jsonl').read_text().splitlines()
    branches=[json.loads(line)['details'].get('branch') for line in logs]
    assert {'release.git-observed','release.git-published','release.db-activated'}<=set(branches)
    assert all('fixture_hashes' not in line for line in logs)


def test_git_reconciliation_refuses_foreign_ref_without_changing_database(posix_tmp_path):
    root=posix_tmp_path
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    service,first,_=approved_release(root/'.local/m')
    service.git=ReleaseGit(root)
    service.activate(first,0,'owner','approver')
    foreign=subprocess.run(['git','-C',str(root),'hash-object','-w','--stdin'],input=b'{}',
                           check=True,capture_output=True).stdout.strip().decode()
    subprocess.run(['git','-C',str(root),'update-ref',REF,foreign],check=True)
    with pytest.raises(ValueError,match='committed activation ancestor'):
        service.reconcile_git()
    assert service.active()=={'hash':first,'revision':1}
    with pytest.raises(ValueError,match='committed activation ancestor'):
        service.activate(first,1,'owner','approver',rollback=True)


def test_git_reconciliation_recovers_published_event_after_ref_update(posix_tmp_path):
    root=posix_tmp_path
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    service,first,manifest=approved_release(root/'.local/m')
    service.git=ReleaseGit(root)
    service.activate(first,0,'owner','approver')
    second=service.register({**manifest,'parent_release':first,'seed':29})
    service.approve(second,'owner','approver','new release')
    original=service.store._event
    def fail_after_git(db, identifier, kind, payload, correlation=None):
        if kind=='release.git.published':
            raise RuntimeError('controlled event transaction failure')
        return original(db,identifier,kind,payload,correlation)
    with patch.object(service.store,'_event',side_effect=fail_after_git):
        with pytest.raises(RuntimeError,match='controlled event transaction failure'):
            service.activate(second,1,'owner','approver')
    assert service.active()=={'hash':second,'revision':2}
    assert service.git_status()['git_hash']==second
    assert [e['type'] for e in service.store.events(second)].count('release.git.published')==0
    service.reconcile_git()
    service.reconcile_git()
    events=service.store.events(second)
    assert [e['type'] for e in events].count('activated')==1
    recovered=[e for e in events if e['type']=='release.git.published']
    assert len(recovered)==1 and recovered[0]['payload']=={'revision':2,'previous':first,'recovered':True}


def test_release_reconcile_endpoint_requires_approver_and_token(posix_tmp_path):
    root=posix_tmp_path
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    with TestClient(create_app(root,'release-unit',role='operator')) as client:
        path='/api/m/releases/reconcile'
        assert client.post(path,json={'expected_revision':0}).status_code==401
        assert client.post(path,headers={'Authorization':'Bearer release-unit'},
                           json={'expected_revision':0}).status_code==403
        assert client.get('/api/m/releases/git',headers={'Authorization':'Bearer release-unit'}).json()=={
            'hash':None,'revision':0,'git_enabled':True,'git_hash':None,'synchronized':True}
