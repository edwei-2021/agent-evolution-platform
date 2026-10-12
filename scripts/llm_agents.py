"""Five supervised roles for one bounded, actual model Skill reflection run."""
from step_trace import traced
import argparse
import json
from pathlib import Path
from llm_engine import TASKS, Runner, content, messages, progress, provenance, reflection_messages, score, skill, splits, verify
from skill_engine import write


def load(directory, filename):
    return json.loads((directory / filename).read_text())


@traced('llm','role.execute')
def run_role(role, directory):
    config = load(directory, 'llm-config.json')
    if config['provenance'] != provenance(config['profile']):
        raise ValueError('Code/data changed after freezing this run')
    base, data = config['baseline']['skill'], splits(config['profile'])
    runner = Runner(directory, config)
    progress(directory, phase=role)
    if role == 'coordinator':
        (directory / 'llm-baseline.md').write_text(base['body'])
        write(directory / 'llm-manifest.json', config)
        progress(directory, model=config['provider']['config']['model'], callBudget=config['callBudget'])
        print('Frozen model settings, baseline, data splits and call/time budgets; no connectivity probes.', flush=True)
    elif role == 'worker':
        training = runner.evaluate(base, data['train'], 'C0', 'train')
        validation = runner.evaluate(base, data['validation'], 'C0', 'validation')
        write(directory / 'llm-baseline-evaluation.json', {'train': training, 'validation': validation})
        progress(directory, candidates=[{'id': 'C0', 'skill': base, 'training': score(training), 'validation': score(validation)}],
                 trainingFailures=[r for r in training if not r['passed']][:8])
    elif role == 'reflector':
        # Validation/held-out outputs never cross this reflection boundary.
        training = load(directory, 'llm-baseline-evaluation.json')['train']
        reply = runner.call('reflection', reflection_messages(base, training))
        value = json.loads(content(reply['response']))
        if not isinstance(value, dict) or set(value) != {'body'}:
            raise ValueError('Reflection must return exactly one body field')
        candidate = skill(value['body'])
        write(directory / 'llm-search.json', {'candidate': candidate, 'parentHash': base['hash']})
        (directory / 'llm-candidate.md').write_text(candidate['body'])
        state = progress(directory)
        progress(directory, candidates=state['candidates'] + [{'id': 'C1', 'skill': candidate, 'training': None, 'validation': None}])
        print('Candidate generated from training failures only; metadata frozen.', flush=True)
    elif role == 'evaluator':
        candidate = load(directory, 'llm-search.json')['candidate']
        baseline = load(directory, 'llm-baseline-evaluation.json')
        training = runner.evaluate(candidate, data['train'], 'C1', 'train')
        validation = runner.evaluate(candidate, data['validation'], 'C1', 'validation')
        candidates = [{'id': 'C0', 'skill': base, 'training': score(baseline['train']), 'validation': score(baseline['validation'])},
                      {'id': 'C1', 'skill': candidate, 'training': score(training), 'validation': score(validation)}]
        selected = 'C1' if candidates[1]['validation']['passed'] > candidates[0]['validation']['passed'] else 'C0'
        progress(directory, candidates=candidates, selectedId=selected)
        runner.evaluate(base, data['heldout'], 'C0', 'heldout')
        if selected == 'C1':
            runner.evaluate(candidate, data['heldout'], 'C1', 'heldout')
        result = verify(directory)
        write(directory / 'llm-evaluation.json', result)
        progress(directory, result=result)
        print(f'Actual output scores verified; selected {selected}; {result["decision"]}.', flush=True)
    elif role == 'reviewer':
        result = verify(directory)
        if result != load(directory, 'llm-evaluation.json'):
            raise ValueError('Stored scores differ from raw model evidence')
        write(directory / 'review.json', result)
        progress(directory, result=result)
        print('Request isolation and raw-output score checks passed; no new inference and no automatic activation.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=list(TASKS), required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run_role(args.role, args.run_dir.resolve())
