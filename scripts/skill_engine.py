"""Bounded declarative skill execution and training-only rule search; no model calls."""
import hashlib
import json
from pathlib import Path
import platform
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'skills/title-normalizer/dataset.json'
NAME = 'normalize-support-title'
DESCRIPTION = 'Normalize support titles using a fixed sequence of explicit text rules.'
ENGINE = 'local-rule-search-v1'
RULES = ('unicode_nfkc', 'casefold', 'trim', 'collapse_whitespace')
INSTRUCTIONS = {
    'unicode_nfkc': 'Apply Unicode NFKC normalization.',
    'casefold': 'Apply Unicode case folding.',
    'trim': 'Remove leading and trailing whitespace.',
    'collapse_whitespace': 'Replace each whitespace sequence with one ASCII space.',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def skill(policy):
    if not isinstance(policy, dict) or set(policy) != set(RULES) or any(type(v) is not bool for v in policy.values()):
        raise ValueError('Skill policy must contain exactly four boolean rules')
    lines = [INSTRUCTIONS[key] for key in RULES if policy[key]] or ['Return the input unchanged.']
    body = '\n'.join(f'{i+1}. {text}' for i, text in enumerate(lines)) + '\n'
    value = {'name': NAME, 'description': DESCRIPTION, 'body': body, 'policy': dict(policy)}
    return {**value, 'hash': digest(value)}


def baseline():
    return skill({key: False for key in RULES})


def validate_skill(value):
    if not isinstance(value, dict) or value != skill(value.get('policy')):
        raise ValueError('Skill body, metadata or hash does not match its executable policy')
    return value


def markdown(value):
    validate_skill(value)
    return f'---\nname: {NAME}\ndescription: {DESCRIPTION}\n---\n\n# Instructions\n\n{value["body"]}'


def execute(value, text):
    validate_skill(value)
    if not isinstance(text, str) or len(text) > 500:
        raise ValueError('Task input must be a string of at most 500 characters')
    policy = value['policy']
    if policy['unicode_nfkc']:
        text = unicodedata.normalize('NFKC', text)
    if policy['casefold']:
        text = text.casefold()
    if policy['trim']:
        text = text.strip()
    if policy['collapse_whitespace']:
        text = re.sub(r'\s+', ' ', text)
    return text


def dataset():
    value = json.loads(DATASET.read_text())
    if value.get('revision') != 'title-normalizer-v1' or set(value.get('splits', {})) != {'train', 'validation', 'heldout'}:
        raise ValueError('Unexpected dataset contract')
    ids, groups = set(), set()
    for split, count in [('train', 20), ('validation', 10), ('heldout', 20)]:
        rows = value['splits'][split]
        if len(rows) != count:
            raise ValueError('Dataset split size mismatch')
        for row in rows:
            if set(row) != {'id', 'group', 'input', 'expected'} or row['id'] in ids or row['group'] in groups or not all(isinstance(v, str) and 0 < len(v) <= 500 for v in row.values()):
                raise ValueError('Duplicate task/group or invalid dataset row')
            ids.add(row['id']);groups.add(row['group'])
    return value


def provenance():
    data = dataset()
    return {'engine': ENGINE, 'datasetRevision': data['revision'], 'datasetHash': digest(data),
            'splitHashes': {key: digest(rows) for key, rows in data['splits'].items()},
            'splitSizes': {key: len(rows) for key, rows in data['splits'].items()},
            'evaluatorHash': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'runnerHash': hashlib.sha256((ROOT / 'scripts/skill_agents.py').read_bytes()).hexdigest(),
            'runtimeHash': hashlib.sha256((ROOT / 'scripts/runtime_service.py').read_bytes()).hexdigest(),
            'auditHash': hashlib.sha256((ROOT / 'scripts/skill_audit.py').read_bytes()).hexdigest(),
            'pythonVersion': platform.python_version(), 'unicodeVersion': unicodedata.unidata_version,
            'model': None, 'frameworkConnected': False}


def distance(left, right):
    """Levenshtein distance is training feedback, never an invented success score."""
    previous = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (char != other)))
        previous = current
    return previous[-1]


def evaluate(value, rows):
    records = []
    for row in rows:
        output = execute(value, row['input'])
        records.append({'taskId': row['id'], 'input': row['input'], 'expected': row['expected'],
                        'output': output, 'passed': output == row['expected'],
                        'distance': distance(output, row['expected']), 'skillHash': value['hash']})
    passed = sum(row['passed'] for row in records)
    return {'passed': passed, 'total': len(records), 'score': passed / len(records),
            'loss': sum(row['distance'] for row in records), 'records': records}


def propose(current, training_feedback):
    """Only training records enter candidate generation; one allowlisted rule changes."""
    validate_skill(current)
    rows = [{'id': row['taskId'], 'input': row['input'], 'expected': row['expected']} for row in training_feedback['records']]
    choices = []
    for rule in RULES:
        if current['policy'][rule]:
            continue
        trial = skill({**current['policy'], rule: True})
        # These training probes are real evaluations and count toward the budget.
        result = evaluate(trial, rows)
        choices.append((result['loss'], rule, trial, result))
    improving = [item for item in choices if item[0] < training_feedback['loss']]
    selected = min(improving, key=lambda item: (item[0], RULES.index(item[1]))) if improving else None
    return selected, [{'rule': item[1], 'skill': item[2], 'training': item[3]} for item in choices]


def write(path, value):
    """Readers always observe a complete progress/evidence file."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)
