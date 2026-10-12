from fastapi.testclient import TestClient
from platform_m.api import create_app
from platform_m.worker import once
from platform_m.evidence import Artifacts, redact
from tests_m.test_m2 import TASK

def test_api_auth_idempotency_worker_and_sse_replay(tmp_path):
    app = create_app(tmp_path, 'unit-token')
    with TestClient(app) as client:
        assert client.get('/api/m/health').status_code == 200
        assert client.get('/api/m/checks').status_code == 401
        headers = {'Authorization':'Bearer unit-token','Idempotency-Key':'one','X-Request-ID':'correlated'}
        body = {'task':TASK,'release':{'skill_hash':'b'*64},'environment':{'adapter':'mock'}}
        first = client.post('/api/m/jobs', json=body, headers=headers)
        assert first.status_code == 202
        assert first.headers['X-Request-ID'] == 'correlated'
        identifier = first.json()['id']
        assert client.post('/api/m/jobs', json=body, headers=headers).json()['id'] == identifier
        assert once(app.state.store, Artifacts(tmp_path/'.local/m/artifacts'))
        assert client.get('/api/m/jobs/'+identifier, headers=headers).json()['state'] == 'completed'
        initial = client.get('/api/m/jobs/'+identifier+'/events', headers=headers)
        assert initial.status_code == 200 and 'data:' in initial.text
        cursor = app.state.store.events(identifier)[1]['seq']
        replay = client.get(f'/api/m/jobs/{identifier}/events?after={cursor}', headers=headers)
        assert f'id: {cursor}\n' not in replay.text
        assert 'correlated' in str(app.state.store.events('correlated'))

def test_cross_origin_and_role_escalation_rejected(tmp_path):
    app = create_app(tmp_path, 'unit-token')
    with TestClient(app) as client:
        assert client.get('/api/m/health', headers={'Origin':'https://outside.example'}).status_code == 403
        assert client.get('/api/m/health', headers={'Host':'outside.example'}).status_code == 403
        response = client.post('/api/m/releases/'+'a'*64+'/approve',
            json={'rationale':'test','role':'approver'},headers={'Authorization':'Bearer unit-token'})
        assert response.status_code == 400

def test_secret_redaction_keeps_original_private_material_out():
    value = redact({'api_key':'secret-value','message':'password=hidden Bearer private-value'})
    assert 'secret-value' not in str(value) and 'hidden' not in str(value) and 'private-value' not in str(value)
