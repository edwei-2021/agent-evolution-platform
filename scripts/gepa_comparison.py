"""Paired final-task comparison; no model calls, filesystem reads or scoring."""
import math

POLICY = 'paired-zero-regression-v1'
OUTCOMES = {(0, 1): 'improved', (1, 0): 'regressed',
            (1, 1): 'retained-pass', (0, 0): 'retained-fail'}


def paired_final(data, ledger, repetitions=1):
    """Use only independently verified final rows, never search trajectories."""
    if type(repetitions) is not int or not 1 <= repetitions <= 3:
        raise ValueError('Invalid frozen final repetition count')
    tasks = {t['id']: (split, t) for split in ('validation', 'heldout') for t in data[split]}
    if len(tasks) != sum(len(data[s]) for s in ('validation', 'heldout')):
        raise ValueError('Duplicate final task identity')
    by_label = {label: {} for label in ('baseline', 'selected')}
    identities = set()
    for row in ledger:
        if row['stage'] == 'search':
            continue
        label, task_id, rollout_id = row['stage'], row['taskId'], row['id']
        rep = row.get('repetition', 0)
        if (label not in by_label or task_id not in tasks or type(rep) is not int or
                not 0 <= rep < (repetitions if tasks[task_id][0] == 'heldout' else 1) or
                (task_id, rep) in by_label[label]
                or rollout_id in identities or type(row['score']) is not int or row['score'] not in (0, 1)):
            raise ValueError('Invalid paired final evidence')
        identities.add(rollout_id)
        by_label[label][task_id, rep] = row
    expected={(task_id, rep) for task_id,(split,_) in tasks.items()
              for rep in range(repetitions if split=='heldout' else 1)}
    if any(set(rows) != expected for rows in by_label.values()):
        raise ValueError('Incomplete paired final evidence')
    rows = []
    splits = {split: {outcome: 0 for outcome in OUTCOMES.values()} for split in ('validation', 'heldout')}
    for task_id, (split, task) in tasks.items():
        for rep in range(repetitions if split=='heldout' else 1):
            before, after = (by_label[label][task_id,rep] for label in ('baseline', 'selected'))
            outcome = OUTCOMES[before['score'], after['score']]
            rows.append({'taskId': task_id, 'split': split, 'group': task['group'],
                         **{k: task[k] for k in ('difficulty', 'topic') if k in task},
                         'baseline': before['score'], 'selected': after['score'], 'outcome': outcome,
                         'baselineRolloutId': before['id'], 'selectedRolloutId': after['id'],
                         **({'repetition':rep} if repetitions>1 else {})})
            splits[split][outcome] += 1
    return {'policy': POLICY, 'splits': splits, 'tasks': rows,
            **({'repetitions':repetitions,'uncertainty':_uncertainty(by_label,data,repetitions)} if repetitions>1 else {})}


def _uncertainty(by_label, data, repetitions):
    heldout=[t['id'] for t in data['heldout']]
    stable={label:sum(all(by_label[label][task,rep]['score'] for rep in range(repetitions))
                      for task in heldout) for label in by_label}
    def wilson(passed,total):
        z=1.96;p=passed/total;den=1+z*z/total
        center=(p+z*z/(2*total))/den
        radius=z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/den
        return [max(0,center-radius),min(1,center+radius)]
    return {'allRepetitionsPassed':stable,
            'taskWilson95':{label:wilson(count,len(heldout)) for label,count in stable.items()},
            'note':'Wilson intervals use tasks passing every repetition; correlated task families limit interpretation.'}


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
