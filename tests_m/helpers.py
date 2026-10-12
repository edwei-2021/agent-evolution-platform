from platform_m.dataset import built_in
from platform_m.evidence import Artifacts, digest
from platform_m.store import Store
from platform_m.contracts import Evaluation
from platform_m.releases import Releases

def stack(tmp_path):
    store = Store(tmp_path/'control.sqlite3')
    artifacts = Artifacts(tmp_path/'artifacts')
    dataset = built_in(artifacts)
    return store, artifacts, dataset

def evaluations(artifacts, dataset_hash, lose=None):
    manifest = artifacts.get(dataset_hash)
    evaluator = artifacts.put({'image': 'test-evaluator', 'mode': 'test-only'})
    evidence = artifacts.put({'test-only': True, 'verdict': 'verified test fixture'})
    values = []
    tasks = [t for t in manifest['tasks'] if t['split'] == 'independent_test']
    for label in ('baseline', 'candidate'):
        for i, task in enumerate(tasks):
            for rep in range(3):
                score = int(label == 'candidate' or i == 0)
                if lose is not None and label == 'candidate' and i == lose:
                    score = 0
                values.append(Evaluation(id=f'{label}-{task["id"]}-{rep}', run_id=f'{label}-{rep}', task_id=task['id'],
                    repetition=rep, label=label, split='independent_test', verdict='pass' if score else 'fail', score=score,
                    evaluator_hash=evaluator, dataset_hash=dataset_hash, snapshot_hash=digest({'policy': 'fixed'}),
                    artifacts=[evidence], failure_category='none' if score else 'assertion').model_dump())
    return values

def approved_release(tmp_path, parent=None):
    store, artifacts, ds = stack(tmp_path)
    values = evaluations(artifacts, ds)
    for label in ('baseline','candidate'):
        for task in artifacts.get(ds)['tasks']:
            if task['split'] == 'validation':
                score = int(label == 'candidate')
                values.append({**values[0], 'id':f'{label}-validation-{task["id"]}', 'task_id':task['id'],
                    'label':label, 'split':'validation', 'repetition':0, 'score':score,
                    'verdict':'pass' if score else 'fail', 'failure_category':'none' if score else 'assertion'})
    for value in values:
        store.evaluation(value)
    asset = artifacts.put({'test-policy': True})
    release = {'skill_hash': asset, 'workflow_hash': asset, 'runtime_hash': asset, 'model_policy_hash': asset,
        'tool_policy_hash': asset, 'evaluator_hash': values[0]['evaluator_hash'], 'dataset_hash': ds,
        'memory_snapshot_hash': asset, 'fixture_hashes': [t['fixture_hash'] for t in artifacts.get(ds)['tasks']],
        'budgets': {'search_tasks': 80}, 'result_ids': [v['id'] for v in values], 'parent_release': parent}
    service = Releases(store, artifacts, tmp_path/'signing.key', allow_test_evidence=True)
    service.init_key()
    identifier = service.register(release)
    service.approve(identifier, 'tester', 'approver', 'test-only evidence')
    return service, identifier, release
