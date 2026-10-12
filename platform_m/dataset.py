"""Versioned family-separated fixtures and safe score-only reflective feedback."""
import math
from .contracts import Task, Evaluation
from .evidence import digest

SPLITS = {'search': 20, 'validation': 10, 'independent_test': 20}

def import_dataset(value, artifacts):
    if set(value) != {'version', 'tasks'} or not isinstance(value['version'], str) or not value['version']:
        raise ValueError('Invalid dataset manifest')
    tasks = [Task.model_validate(t) for t in value['tasks']]
    if len(tasks) != 50 or {s: sum(t.split == s for t in tasks) for s in SPLITS} != SPLITS:
        raise ValueError('Use exactly 20/10/20 tasks')
    families, fixtures, ids = {}, {}, set()
    for task in tasks:
        if task.id in ids:
            raise ValueError('Duplicate task ID')
        ids.add(task.id)
        for registry, key in ((families, task.family), (fixtures, task.fixture_hash)):
            if key in registry and registry[key] != task.split:
                raise ValueError('Cross-split family/fixture leakage: ' + task.id)
            registry[key] = task.split
        fixture = artifacts.get(task.fixture_hash)
        if set(fixture) != {'baseline', 'prompt', 'visible', 'hidden'}:
            raise ValueError('Unknown fixture fields')
        if fixture['prompt'] != task.requirement or task.allowed_files != ['solution.py']:
            raise ValueError('Task fixture/policy mismatch')
        from scripts.repair_fixture import validate_source
        validate_source(fixture['baseline'])
        for split in ('visible', 'hidden'):
            if not isinstance(fixture[split], list) or not 1 <= len(fixture[split]) <= 50:
                raise ValueError('Missing or oversized fixture tests')
            for case in fixture[split]:
                if not isinstance(case, list) or len(case) != 2 or not isinstance(case[0], list) or len(case[0]) != 3:
                    raise ValueError('Malformed fixture case')
                if any(type(v) is not int or abs(v) > 1000000 for v in case[0]):
                    raise ValueError('Unbounded fixture input')
                if type(case[1]) is not int and case[1] != 'ValueError':
                    raise ValueError('Unsupported expected outcome')
    normalized = {'version': value['version'], 'tasks': [t.model_dump() for t in tasks]}
    return artifacts.put(normalized)

def built_in(artifacts):
    from scripts.gepa_dataset import dataset, DATASET_VERSION
    tasks = []
    for split, rows in dataset('full').items():
        canonical_split = {'train': 'search', 'validation': 'validation', 'heldout': 'independent_test'}[split]
        for row in rows:
            fixture_hash = artifacts.put(row['fixture'])
            tasks.append(Task(id=row['id'], family=row['group'], split=canonical_split,
                              fixture_hash=fixture_hash, requirement=row['fixture']['prompt']).model_dump())
    return import_dataset({'version': DATASET_VERSION, 'tasks': tasks}, artifacts)

def feedback(task, evaluation):
    task = Task.model_validate(task)
    e = Evaluation.model_validate(evaluation)
    if task.split != 'search' or e.split != 'search' or e.task_id != task.id:
        raise ValueError('Reflection can only use matching search records')
    if e.verdict == 'invalid_evaluation':
        raise ValueError('Invalid evaluation cannot enter reflection')
    # No raw tool output, assertions, requirement, hidden inputs, paths or secrets.
    return {'task_id': task.id, 'score': e.score, 'failure_category': e.failure_category}

def wilson(passed, total):
    z = 1.96
    p = passed/total
    center = (p+z*z/(2*total))/(1+z*z/total)
    radius = z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/(1+z*z/total)
    return [max(0, center-radius), min(1, center+radius)]

def compare(values, manifest, repetitions=3):
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise ValueError('Invalid repetition policy')
    task_ids = {t['id'] for t in manifest['tasks'] if t['split'] == 'independent_test'}
    if len(task_ids) != 20:
        raise ValueError('Final comparison requires 20 independent tasks')
    rows = [Evaluation.model_validate(v) for v in values]
    expected = {(label, task, rep) for label in ('baseline', 'candidate') for task in task_ids for rep in range(repetitions)}
    keys = [(v.label, v.task_id, v.repetition) for v in rows]
    if len(set(keys)) != len(keys) or set(keys) != expected or any(v.split != 'independent_test' for v in rows):
        raise ValueError('Incomplete, duplicate or non-final comparison')
    if any(v.verdict == 'invalid_evaluation' for v in rows):
        raise ValueError('Infrastructure/integrity failure blocks comparison')
    for name in ('evaluator_hash', 'dataset_hash', 'snapshot_hash'):
        if len({getattr(v, name) for v in rows}) != 1:
            raise ValueError('Comparison snapshot mismatch: ' + name)
    if rows[0].dataset_hash != digest(manifest):
        raise ValueError('Dataset snapshot mismatch')
    scores = {(v.label, v.task_id, v.repetition): v.score for v in rows}
    regressions = [{'task_id': task, 'repetition': rep} for task in sorted(task_ids) for rep in range(repetitions)
                   if scores['baseline', task, rep] == 1 and scores['candidate', task, rep] == 0]
    totals = {label: sum(v.score for v in rows if v.label == label) for label in ('baseline', 'candidate')}
    total = 20*repetitions
    # Intervals across task means avoid treating repeated runs as independent tasks.
    task_means = {label: {task: sum(scores[label, task, rep] for rep in range(repetitions))/repetitions
                         for task in task_ids} for label in totals}
    return {'valid': True, 'eligible': not regressions and totals['candidate'] > totals['baseline'],
            'regressions': regressions, 'totals': totals, 'executions_per_label': total,
            'task_count': 20, 'repetitions': repetitions, 'task_mean_success': task_means,
            'all_repetitions_pass_interval': {label: wilson(sum(v == 1 for v in task_means[label].values()), 20)
                                            for label in totals},
            'uncertainty_note': 'Wilson interval uses tasks passing every repetition; synthetic families remain correlated.',
            'evaluator_hash': rows[0].evaluator_hash, 'dataset_hash': rows[0].dataset_hash,
            'snapshot_hash': rows[0].snapshot_hash, 'result_ids': sorted(v.id for v in rows)}
