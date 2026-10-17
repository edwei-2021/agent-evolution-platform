"""Operator-managed, revisioned challenge bank and immutable GEPA datasets."""
import copy
import json
from pathlib import Path
import re
import uuid
from challenge_policy import POLICY, check_json, validate_source
from repair_fixture import digest

VERSION = 'python-challenges-v1'
SPLITS = ('train', 'validation', 'heldout')
FIELDS = {'id', 'title', 'difficulty', 'topic', 'group', 'split', 'enabled', 'prompt', 'baseline',
          'reference', 'visible', 'hidden', 'sources', 'attribution'}


def fixture(question):
    rules = ('\nImplement only solve(data) in solution.py. This task-specific signature overrides any legacy '
             'clamp example in the generic Skill. Do not mutate input. Use pure Python loops, conditionals, '
             'lists/dicts/sets, indexing/slicing, approved data methods and builtins. No imports, files, '
             'network, shell, classes, recursion, comprehensions or private attributes. '
             'Use read_solution, write_solution and run_tests; summarize after visible tests pass.')
    return {'policy': POLICY, 'baseline': question['baseline'],
            'prompt': f'Task ID: {question["id"]}\n{question["prompt"]}' + rules,
            'visible': copy.deepcopy(question['visible']), 'hidden': copy.deepcopy(question['hidden'])}


def validate_question(value, *, execute=False):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Challenge fields must match the editor schema')
    if not isinstance(value['id'], str) or not re.fullmatch(r'CH-[A-Za-z0-9-]{1,80}', value['id']):
        raise ValueError('Invalid challenge ID')
    for key, maximum in [('title', 160), ('topic', 80), ('group', 80), ('prompt', 4000), ('attribution', 1000)]:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > maximum:
            raise ValueError(f'{key} must be nonempty and at most {maximum} characters')
    if value['difficulty'] not in ('easy', 'medium', 'hard') or value['split'] not in SPLITS or type(value['enabled']) is not bool:
        raise ValueError('Choose easy/medium/hard, train/validation/heldout and an enabled flag')
    if (not isinstance(value['sources'], list) or len(value['sources']) > 8 or
            any(not isinstance(s, str) or len(s) > 500 or not s.startswith('https://') for s in value['sources'])):
        raise ValueError('Use at most eight HTTPS research/source links')
    validate_source(value['baseline'])
    validate_source(value['reference'])
    for split in ('visible', 'hidden'):
        cases = value[split]
        if not isinstance(cases, list) or not 2 <= len(cases) <= 20:
            raise ValueError('Each task needs 2..20 visible and 2..20 held-out input cases')
        for case in cases:
            if not isinstance(case, dict) or set(case) not in ({'input', 'expected'}, {'input', 'raises'}):
                raise ValueError('Each case has input plus expected, or input plus raises="ValueError"')
            check_json(case['input'])
            if 'expected' in case:
                check_json(case['expected'])
            elif case['raises'] != 'ValueError':
                raise ValueError('Only ValueError is a supported expected exception')
    if len(json.dumps(value).encode()) > 64000:
        raise ValueError('Challenge exceeds 64 KB')
    if execute:
        from repair_engine import trusted_test_batch
        f = fixture(value)
        jobs = [{'source': value[label], 'split': split, 'fixture': f}
                for label in ('reference', 'baseline') for split in ('visible', 'hidden')]
        try:
            results = trusted_test_batch(jobs)
        except Exception as exc:
            raise ValueError('Bounded reference/baseline validation failed: ' + str(exc)) from exc
        if any(r['passed'] != r['total'] for r in results[:2]):
            raise ValueError('Reference solution must pass every visible and hidden case')
        if all(r['passed'] == r['total'] for r in results[2:]):
            raise ValueError('Starting program already passes every case; supply a genuine defect')
    return copy.deepcopy(value)


def validate_snapshot(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'revision', 'data', 'hash'} or
            value.get('version') != VERSION or type(value.get('revision')) is not int or value['revision'] < 1):
        raise ValueError('Invalid frozen challenge dataset')
    if value.get('hash') != digest({k: value[k] for k in ('version', 'revision', 'data')}):
        raise ValueError('Frozen challenge dataset hash changed')
    data = value['data']
    if not isinstance(data, dict) or set(data) != set(SPLITS):
        raise ValueError('All three challenge splits are required')
    identities, groups = set(), {}
    if any(not isinstance(rows, list) for rows in data.values()):
        raise ValueError('Challenge splits must contain task lists')
    if sum(len(rows) for rows in data.values()) > 50:
        raise ValueError('Use at most 50 enabled challenges per run')
    for split, rows in data.items():
        if not isinstance(rows, list) or not 2 <= len(rows) <= (30 if split == 'train' else 20):
            raise ValueError('Enable at least two tasks in every split (train <=30, others <=20)')
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'id', 'title', 'difficulty', 'topic', 'group', 'fixture'} or
                    any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('id', 'title', 'difficulty', 'topic', 'group')) or
                    row['difficulty'] not in ('easy', 'medium', 'hard') or not isinstance(row['fixture'], dict)):
                raise ValueError('Invalid frozen challenge row')
            if row['id'] in identities or row['group'] in groups and groups[row['group']] != split:
                raise ValueError('Duplicate tasks or related task groups cross dataset splits')
            identities.add(row['id'])
            groups[row['group']] = split
            if row['fixture'].get('policy') != POLICY or 'reference' in row or 'reference' in row['fixture']:
                raise ValueError('Frozen tasks require challenge policy and must not include reference code')
            validate_source(row['fixture']['baseline'])
    if len(data['validation']) + len(data['heldout']) > 30:
        raise ValueError('Validation plus held-out tasks must not exceed 30')
    return data


class ChallengeBank:
    def __init__(self, service):
        self.service = service
        self._summary = None
        with service.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS challenge_bank (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, data TEXT NOT NULL)')
            if not db.execute('SELECT 1 FROM challenge_bank').fetchone():
                root = Path(__file__).resolve().parents[1]
                seeds = json.loads((root / 'data/python-challenges-v1.json').read_text())
                for question in seeds:
                    validate_question(question)
                db.execute('INSERT INTO challenge_bank VALUES (1,1,?)', (json.dumps(seeds, ensure_ascii=False),))

    def snapshot(self):
        with self.service.lock, self.service.connect() as db:
            revision, raw = db.execute('SELECT revision,data FROM challenge_bank WHERE singleton=1').fetchone()
        return {'schemaVersion': 1, 'version': VERSION, 'revision': revision, 'questions': json.loads(raw)}

    def summary(self):
        snap = self.snapshot()
        if self._summary is not None and self._summary['revision'] == snap['revision']:
            return copy.deepcopy(self._summary)
        counts = {s: sum(q['enabled'] and q['split'] == s for q in snap['questions']) for s in SPLITS}
        error = None
        try:
            self.freeze(snap['revision'])
        except ValueError as exc:
            error = str(exc)
        self._summary = {'revision': snap['revision'], 'version': VERSION, 'counts': counts,
                         'total': len(snap['questions']), 'ready': error is None, 'error': error}
        return copy.deepcopy(self._summary)

    def check_revision(self, revision):
        if type(revision) is not int or self.snapshot()['revision'] != revision:
            raise RuntimeError('Challenge bank changed; refresh before submitting')

    def freeze(self, revision):
        snap = self.snapshot()
        if type(revision) is not int or revision != snap['revision']:
            raise RuntimeError('Challenge bank changed; refresh before submitting')
        data = {s: [] for s in SPLITS}
        for question in snap['questions']:
            if question['enabled']:
                row = {k: question[k] for k in ('id', 'title', 'difficulty', 'topic', 'group')}
                row['fixture'] = fixture(question)
                data[question['split']].append(row)
        frozen = {'version': VERSION, 'revision': revision, 'data': data}
        frozen['hash'] = digest(frozen)
        validate_snapshot(frozen)
        return frozen

    def mutate(self, revision, question=None, identifier=None, delete=False):
        self.check_revision(revision)
        if not delete:
            question = dict(question) if isinstance(question, dict) else {}
            question['id'] = identifier or 'CH-' + str(uuid.uuid4())
            question = validate_question(question, execute=True)
        with self.service.lock:
            self.check_revision(revision)
            snap = self.snapshot()
            rows = snap['questions']
            if identifier:
                found = next((i for i, q in enumerate(rows) if q['id'] == identifier), None)
                if found is None:
                    raise KeyError('Challenge not found')
                if delete:
                    rows.pop(found)
                else:
                    rows[found] = question
            else:
                if len(rows) >= 100:
                    raise ValueError('Challenge bank is limited to 100 questions')
                rows.append(question)
            with self.service.connect() as db:
                db.execute('UPDATE challenge_bank SET revision=?,data=? WHERE singleton=1',
                           (revision + 1, json.dumps(rows, ensure_ascii=False)))
        return self.snapshot()
