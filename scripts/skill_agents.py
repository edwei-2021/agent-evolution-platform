"""Five fixed native roles for measured declarative skill evolution."""
from step_trace import traced
import argparse
import json
from pathlib import Path

from skill_engine import ENGINE, dataset, digest, evaluate, markdown, propose, provenance, validate_skill, write

TASKS = {'coordinator': 'Freeze active Skill and dataset/evaluator hashes',
         'worker': 'Search one-rule Skill mutations using training feedback',
         'evaluator': 'Select on validation, then run held-out checks',
         'reflector': 'Compare measured evidence and Skill changes',
         'reviewer': 'Recompute evidence and gate human version approval'}


def load(directory, name):
    return json.loads((directory / name).read_text())


def compact(result):
    return {key: result[key] for key in ('passed', 'total', 'score', 'loss')}


def progress(directory, **updates):
    path = directory / 'progress.json'
    value = load(directory, 'progress.json') if path.exists() else {'engine': ENGINE, 'phase': 'queued', 'candidates': [], 'evaluations': {'training': 0, 'validation': 0, 'heldout': 0, 'verification': 0}, 'selectedId': None, 'eligible': None}
    value.update(updates)
    write(path, value)
    return value


def assess(candidates, validation, heldout):
    results = [{'id': c['id'], 'result': evaluate(c['skill'], validation)} for c in candidates]
    # Earlier/smaller candidates win ties; search receives no validation or held-out feedback.
    selected = max(range(len(candidates)), key=lambda i: (results[i]['result']['passed'], -results[i]['result']['loss'], -i))
    base = evaluate(candidates[0]['skill'], heldout)
    chosen = evaluate(candidates[selected]['skill'], heldout)
    eligible = selected != 0 and results[selected]['result']['passed'] > results[0]['result']['passed'] and chosen['passed'] >= base['passed']
    return {'validation': results, 'selectedId': candidates[selected]['id'],
            'heldout': {'baseline': base, 'selected': chosen}, 'eligible': eligible,
            'decision': 'ready-for-human-review' if eligible else 'keep-baseline'}


def verified_report(directory):
    config, search, report = (load(directory, name) for name in ('skill-config.json', 'search.json', 'evaluation.json'))
    if config['provenance'] != provenance() or search['baselineHash'] != config['baseline']['skill']['hash']:
        raise ValueError('Dataset, evaluator or baseline changed during the run')
    candidates = search['candidates']
    if not 1 <= len(candidates) <= config['maxCandidates'] + 1 or candidates[0]['skill'] != config['baseline']['skill']:
        raise ValueError('Invalid candidate lineage')
    for i, candidate in enumerate(candidates):
        validate_skill(candidate['skill'])
        if candidate['id'] != f'C{i}' or (i and (sum(candidate['skill']['policy'][key] != candidates[i-1]['skill']['policy'][key] for key in candidate['skill']['policy']) != 1 or any(candidates[i-1]['skill']['policy'][key] and not candidate['skill']['policy'][key] for key in candidate['skill']['policy']))):
            raise ValueError('Candidate is outside the one-rule mutation contract')
    data = dataset()['splits']
    verified = assess(candidates, data['validation'], data['heldout'])
    if report != verified:
        raise ValueError('Stored evaluation differs from trusted recomputation')
    chosen = next(c for c in candidates if c['id'] == verified['selectedId'])
    return config, search, verified, chosen


@traced('skills','role.execute')
def run_role(role, directory):
    config = load(directory, 'skill-config.json')
    if config['provenance'] != provenance():
        raise ValueError('Frozen source/data hashes no longer match')
    base = validate_skill(config['baseline']['skill'])
    if role == 'coordinator':
        write(directory / 'skill-manifest.json', {'task': 'skill-evolution', 'baselineVersionId': config['baseline']['id'],
              'baselineHash': base['hash'], 'maxCandidates': config['maxCandidates'], 'provenance': config['provenance']})
        (directory / 'baseline.md').write_text(markdown(base))
        progress(directory, phase=role, baselineVersionId=config['baseline']['id'], baseline=base, maxCandidates=config['maxCandidates'], provenance=config['provenance'])
        print('Frozen Skill, 20/10/20 task splits and evaluator hashes. No model calls.', flush=True)
    elif role == 'worker':
        # Only this training split crosses the search-function boundary.
        training = dataset()['splits']['train']
        initial = evaluate(base, training)
        candidates = [{'id': 'C0', 'mutation': None, 'skill': base, 'training': compact(initial)}]
        traces = [{'id': 'C0', 'training': initial}]
        probes = []
        counts = {'training': len(training), 'validation': 0, 'heldout': 0, 'verification': 0}
        current, feedback = base, initial
        progress(directory, phase=role, candidates=candidates, evaluations=counts, trainingFailures=[r for r in initial['records'] if not r['passed']][:8])
        for index in range(config['maxCandidates']):
            selected, trials = propose(current, feedback)
            counts['training'] += sum(trial['training']['total'] for trial in trials)
            probes.append({'round': index + 1, 'trials': trials})
            if selected is None:
                progress(directory, candidates=candidates, evaluations=counts)
                print('No training-loss-reducing rule mutation remains; stop search.', flush=True)
                break
            _, mutation, current, feedback = selected
            identifier = f'C{index+1}'
            candidates.append({'id': identifier, 'mutation': mutation, 'skill': current, 'training': compact(feedback)})
            traces.append({'id': identifier, 'training': feedback})
            (directory / f'candidate-{index+1}.md').write_text(markdown(current))
            progress(directory, candidates=candidates, evaluations=counts)
            print(f'{identifier}: enabled {mutation}; measured training {feedback["passed"]}/{feedback["total"]}; total training calls {counts["training"]}', flush=True)
        write(directory / 'search.json', {'baselineHash': base['hash'], 'candidates': candidates, 'evaluations': counts})
        write(directory / 'training-traces.json', traces)
        write(directory / 'training-probes.json', probes)
    elif role == 'evaluator':
        search = load(directory, 'search.json')
        data = dataset()['splits']
        report = assess(search['candidates'], data['validation'], data['heldout'])
        counts = {**search['evaluations'], 'validation': len(search['candidates']) * len(data['validation']), 'heldout': 2 * len(data['heldout'])}
        candidates = [{**candidate, 'validation': compact(result['result'])} for candidate, result in zip(search['candidates'], report['validation'])]
        write(directory / 'evaluation.json', report)
        progress(directory, phase=role, candidates=candidates, selectedId=report['selectedId'], heldout={key: compact(value) for key, value in report['heldout'].items()}, evaluations=counts)
        print(f'Selected {report["selectedId"]} on validation; only then evaluated baseline/selected on held-out tasks.', flush=True)
    elif role == 'reflector':
        report = load(directory, 'evaluation.json')
        summary = {'method': ENGINE, 'decision': report['decision'], 'recommendation': 'Review the measured improvement before approving a local version.' if report['eligible'] else 'Keep the frozen baseline; a non-improving search is a valid outcome.', 'heldoutUsedForSearch': False, 'modelCalls': 0}
        write(directory / 'reflection.json', summary)
        progress(directory, phase=role)
        print(summary['recommendation'], flush=True)
    elif role == 'reviewer':
        config, search, report, chosen = verified_report(directory)
        value = {'checksPassed': True, 'task': 'skill-evolution', 'engine': ENGINE, 'published': False,
                 'eligible': report['eligible'], 'decision': report['decision'], 'selectedId': chosen['id'],
                 'selectedSkill': chosen['skill'], 'baselineVersionId': config['baseline']['id'], 'baselineHash': base['hash'],
                 'baselineValidation': compact(report['validation'][0]['result']),
                 'selectedValidation': compact(next(r['result'] for r in report['validation'] if r['id'] == chosen['id'])),
                 'heldout': {key: compact(v) for key, v in report['heldout'].items()},
                 'provenance': config['provenance'], 'evidenceHash': digest(report)}
        write(directory / 'review.json', value)
        status = progress(directory, phase=role, eligible=report['eligible'], decision=report['decision'])
        counts = {**status['evaluations'], 'verification': len(search['candidates']) * 10 + 40}
        progress(directory, evaluations=counts)
        print(f'Trusted recomputation passed. Decision: {report["decision"]}; human approval required; no auto-activation.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=list(TASKS))
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run_role(args.role, args.run_dir.resolve())


if __name__ == '__main__':
    main()
