import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from platform_m.store import Store
from platform_m.evidence import Artifacts
from platform_m.worker import once
from tests_m.test_m2 import TASK

def test_concurrent_duplicate_submission_is_one_logical_job(tmp_path):
    store = Store(tmp_path/'db')
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: store.submit('same', {'x': 1}), range(20)))
    assert len(set(ids)) == 1
    with pytest.raises(ValueError):
        store.submit('same', {'x': 2})

def test_lifecycle_completion_and_cancel_fence(tmp_path):
    store = Store(tmp_path/'db')
    identifier = store.submit('one', {})
    job = store.claim('worker')
    with pytest.raises(ValueError):
        store.complete(job, {})
    assert store.request_cancel(identifier)=='cancelling'
    assert store.get(identifier)['state']=='cancelling'
    store.heartbeat(job)
    with pytest.raises(ValueError):store.complete(job,{})
    store.transition(identifier,'cancelled',job)
    with pytest.raises(RuntimeError):
        store.heartbeat(job)
    with pytest.raises(ValueError):
        store.transition(identifier, 'running', job)

def test_crash_recovery_resume_preserves_checkpoint_and_rejects_stale_writer(tmp_path):
    store = Store(tmp_path/'db')
    identifier = store.submit('one', {'snapshot': 'fixed'})
    job = store.claim('worker')
    store.checkpoint(job, 0, 'a'*64)
    with store.db() as db:
        db.execute('UPDATE jobs SET lease=? WHERE id=?', (time.time()-1, identifier))
    assert Store(tmp_path/'db').reconcile() == 1
    with pytest.raises(RuntimeError):
        store.complete(job, {})
    store.resume(identifier, store.get(identifier)['request_hash'])
    next_job = store.claim('next')
    assert next_job['fence'] > job['fence']
    store.checkpoint(next_job, 0, 'a'*64)
    with pytest.raises(ValueError):
        store.checkpoint(next_job, 0, 'b'*64)

def test_event_reconnect_and_append_only_evidence(tmp_path):
    store = Store(tmp_path/'db')
    for i in range(10):
        store.event('run', 'chunk', {'i': i, 'api_key': 'private'})
    first = store.events('run', limit=4)
    rest = store.events('run', after=first[-1]['seq'])
    assert len({r['seq'] for r in first+rest}) == 10
    assert 'private' not in json.dumps(first+rest)
    with pytest.raises(sqlite3.IntegrityError), store.db() as db:
        db.execute('DELETE FROM events')

def test_real_queue_worker_persists_execution_facts_without_success_score(tmp_path):
    store = Store(tmp_path/'db')
    identifier = store.submit('one', {'task': TASK, 'release': {'skill_hash':'b'*64}, 'environment': {'adapter':'mock'}})
    assert once(store, Artifacts(tmp_path/'artifacts'))
    assert store.get(identifier)['state'] == 'completed'
    assert not once(store, Artifacts(tmp_path/'artifacts'))
    with store.db() as db:
        result = json.loads(db.execute('SELECT data FROM results').fetchone()[0])
    assert result['status'] == 'succeeded' and 'score' not in result
