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
        return False
    try:
        config = job['payload']
        result = MockAdapter().run(config['task'], config['release'], config['environment'], job['id'], artifacts)
        store.event(job['id'], 'worker.result', {'status': result.status}, job['id'])
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
