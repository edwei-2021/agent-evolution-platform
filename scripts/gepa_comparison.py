"""Paired final-task comparison; no model calls, filesystem reads or scoring."""

POLICY = 'paired-zero-regression-v1'
OUTCOMES = {(0, 1): 'improved', (1, 0): 'regressed',
            (1, 1): 'retained-pass', (0, 0): 'retained-fail'}


def paired_final(data, ledger):
    """Use only independently verified final rows, never search trajectories."""
    tasks = {t['id']: (split, t) for split in ('validation', 'heldout') for t in data[split]}
    if len(tasks) != sum(len(data[s]) for s in ('validation', 'heldout')):
        raise ValueError('Duplicate final task identity')
    by_label = {label: {} for label in ('baseline', 'selected')}
    identities = set()
    for row in ledger:
        if row['stage'] == 'search':
            continue
        label, task_id, rollout_id = row['stage'], row['taskId'], row['id']
        if (label not in by_label or task_id not in tasks or task_id in by_label[label]
                or rollout_id in identities or type(row['score']) is not int or row['score'] not in (0, 1)):
            raise ValueError('Invalid paired final evidence')
        identities.add(rollout_id)
        by_label[label][task_id] = row
    if any(set(rows) != set(tasks) for rows in by_label.values()):
        raise ValueError('Incomplete paired final evidence')
    rows = []
    splits = {split: {outcome: 0 for outcome in OUTCOMES.values()} for split in ('validation', 'heldout')}
    for task_id, (split, task) in tasks.items():
        before, after = (by_label[label][task_id] for label in ('baseline', 'selected'))
        outcome = OUTCOMES[before['score'], after['score']]
        rows.append({'taskId': task_id, 'split': split, 'group': task['group'],
                     **{k: task[k] for k in ('difficulty', 'topic') if k in task},
                     'baseline': before['score'], 'selected': after['score'], 'outcome': outcome,
                     'baselineRolloutId': before['id'], 'selectedRolloutId': after['id']})
        splits[split][outcome] += 1
    return {'policy': POLICY, 'splits': splits, 'tasks': rows}


def release_blockers(policy, baseline, selected, final, comparison=None):
    """Keep historical aggregate rules explicit; new policy forbids lost passes."""
    if policy not in (None, POLICY):
        raise ValueError('Unknown frozen comparison policy')
    blockers = []
    if selected['hash'] == baseline['hash']:
        blockers.append('unchanged-skill')
    if final['selected']['validation']['passed'] <= final['baseline']['validation']['passed']:
        blockers.append('validation-not-improved')
    if final['selected']['heldout']['passed'] < final['baseline']['heldout']['passed']:
        blockers.append('heldout-total-regressed')
    if policy == POLICY:
        if not comparison or comparison.get('policy') != POLICY:
            raise ValueError('Missing paired final evidence')
        for split in ('validation', 'heldout'):
            if comparison['splits'][split]['regressed']:
                blockers.append(split + '-task-regressed')
    return blockers
