"""Lease-fenced deterministic queue worker; real legacy agents remain independent."""
import argparse
from pathlib import Path
import time
from .adapters import MockAdapter
from .store import Store
from .evidence import Artifacts

def once(store, artifacts):
    store.reconcile()
    job = store.claim('mock-worker', adapter='mock')
    if job is None:
        return native_once(store,artifacts)
    try:
        config = job['payload']
        result = MockAdapter().run(config['task'], config['release'], config['environment'], job['id'], artifacts)
        store.event(job['id'], 'worker.result', {'status': result.status}, job['id'])
        if store.get(job['id'])['state']=='cancelling':
            store.transition(job['id'],'cancelled',job)
            return True
        store.transition(job['id'], 'evaluating', job)
        value = result.model_dump()
        evidence = artifacts.put(value)
        store.checkpoint(job, 0, evidence)
        store.complete(job, value)
    except Exception as exc:
        store.event(job['id'], 'worker.error', {'type': type(exc).__name__, 'message': str(exc)})
        if store.get(job['id'])['state'] not in ('cancelled', 'interrupted'):
            store.transition(job['id'], 'failed', job)
    return True

def native_once(store,artifacts):
    """Claim only a configured native job after acquiring the shared model lock."""
    import fcntl
    from scripts.branch_diagnostics import record
    root=store.path.parent.parent.parent
    with store.db() as db:
        row=db.execute("SELECT j.id,c.hash FROM jobs j JOIN checkpoints c ON c.job_id=j.id AND c.ordinal=-1 "
            "WHERE j.state='queued' AND json_extract(j.payload,'$.environment.adapter')='nanobot' ORDER BY j.rowid LIMIT 1").fetchone()
    if row is None:return False
    with (root/'.local/runtime.lock').open('a+') as model_lock:
        try:fcntl.flock(model_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            record(root,'M3','native.admission','model-busy',identifier=row['id']);return False
        job=store.claim_id(row['id'],'nanobot-worker',seconds=180)
        if job is None:return False
        try:
            config=artifacts.get(row['hash'])
            from scripts.run_m_repair import execute_frozen, ROOT
            from scripts.repair_engine import provenance
            from .gates import source_snapshot
            if config['provenance']!=provenance() or config['canonicalSourceHash']!=source_snapshot(ROOT)[0]:
                raise ValueError('Frozen native source changed; no model request dispatched')
            execute_frozen(root,store,artifacts,job,config)
        except Exception as exc:
            record(root,'M3','native.execution','failed',identifier=job['id'],error=exc)
            store.event(job['id'],'worker.error',{'type':type(exc).__name__,'debug_code':'DBG-M-003'})
            if store.get(job['id'])['state'] in ('running','evaluating','cancelling'):
                store.transition(job['id'],'failed',job)
        return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    store = Store(args.root/'.local/m/control.sqlite3')
    artifacts = Artifacts(args.root/'.local/m/artifacts')
    import fcntl
    from .evidence import atomic_write
    stream = (args.root/'.local/m/worker.lock').open('a+')
    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while True:
        atomic_write(args.root/'.local/m/worker.heartbeat', str(time.time()).encode())
        processed = once(store, artifacts)
        if args.once:
            return
        if not processed:
            time.sleep(.5)

if __name__ == '__main__':
    main()
