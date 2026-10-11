"""Server-owned immutable skill versions, revision-checked activation and rollback."""
import json
import uuid

from skill_engine import baseline, validate_skill


class SkillStore:
    def __init__(self, service):
        self.service = service
        with service.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS skill_versions (id TEXT PRIMARY KEY, run_id TEXT UNIQUE, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS skill_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, active_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS skill_actions (revision INTEGER PRIMARY KEY, data TEXT NOT NULL)')
            value = {'id': 'SKV-baseline', 'label': 'S0', 'parentId': None, 'runId': None, 'createdAt': service.timestamp(), 'skill': baseline(), 'evidence': None}
            db.execute('INSERT OR IGNORE INTO skill_versions VALUES (?, ?, ?)', (value['id'], None, json.dumps(value)))
            db.execute('INSERT OR IGNORE INTO skill_state VALUES (1, 1, ?)', (value['id'],))

    def snapshot(self):
        with self.service.lock, self.service.connect() as db:
            revision, active_id = db.execute('SELECT revision, active_id FROM skill_state WHERE singleton=1').fetchone()
            versions = [json.loads(row[0]) for row in db.execute('SELECT data FROM skill_versions ORDER BY rowid')]
            active = next(v for v in versions if v['id'] == active_id)
            actions = [json.loads(row[0]) for row in db.execute('SELECT data FROM skill_actions ORDER BY revision DESC LIMIT 20')]
        return {'schemaVersion': 1, 'engine': 'local-rule-search-v1', 'revision': revision, 'activeVersionId': active_id, 'active': active, 'versions': versions, 'actions': actions}

    def freeze(self, options):
        if not isinstance(options, dict) or set(options) != {'maxCandidates', 'expectedRevision'} or type(options['maxCandidates']) is not int or not 1 <= options['maxCandidates'] <= 4:
            raise ValueError('Use maxCandidates 1–4 and the current expectedRevision')
        self.check_revision(options['expectedRevision'])
        from skill_engine import provenance
        return {'schemaVersion': 1, 'maxCandidates': options['maxCandidates'], 'baseline': self.snapshot()['active'], 'provenance': provenance()}

    def check_revision(self, expected):
        if type(expected) is not int or expected < 1:
            raise ValueError('expectedRevision must be a positive integer')
        if self.service.closed:
            raise RuntimeError('Runtime service is stopping')
        if self.snapshot()['revision'] != expected:
            raise RuntimeError('Skill state changed; refresh before trying again')

    def approve(self, identifier, expected):
        with self.service.lock:
            self.check_revision(expected)
            run = self.service.get_run(identifier)
            if run.get('task') != 'skill-evolution' or run['status'] != 'completed' or not run.get('skillResult', {}).get('eligible'):
                raise RuntimeError('Only a completed, improving and verified skill run can be approved')
            from skill_agents import verified_report, compact
            config, search, report, chosen = verified_report(self.service.local / 'runs' / identifier)
            if not report['eligible'] or config['baseline']['id'] != self.snapshot()['activeVersionId']:
                raise RuntimeError('Run baseline is no longer active or candidate did not improve; start a fresh run')
            with self.service.connect() as db:
                if db.execute('SELECT id FROM skill_versions WHERE run_id=?', (identifier,)).fetchone():
                    raise RuntimeError('This run already has an approved version; use version activation')
                count = db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0]
                if count >= 100:
                    raise RuntimeError('Local version limit (100) reached; archive this workspace before continuing')
                version = {'id': 'SKV-' + str(uuid.uuid4()), 'label': f'S{count}', 'parentId': config['baseline']['id'],
                           'runId': identifier, 'createdAt': self.service.timestamp(), 'skill': chosen['skill'],
                           'evidence': {'baselineValidation': compact(report['validation'][0]['result']),
                                        'selectedValidation': compact(next(r['result'] for r in report['validation'] if r['id'] == chosen['id'])),
                                        'heldout': {key: compact(v) for key, v in report['heldout'].items()}, 'provenance': config['provenance']}}
                db.execute('INSERT INTO skill_versions VALUES (?, ?, ?)', (version['id'], identifier, json.dumps(version)))
                self.move(db, version['id'], expected, 'approve-and-activate')
            return self.snapshot()

    def move(self, db, identifier, revision, action):
        previous = db.execute('SELECT active_id FROM skill_state WHERE singleton=1').fetchone()[0]
        db.execute('UPDATE skill_state SET active_id=?, revision=? WHERE singleton=1 AND revision=?', (identifier, revision + 1, revision))
        value = {'revision': revision + 1, 'action': action, 'from': previous, 'to': identifier, 'at': self.service.timestamp()}
        db.execute('INSERT INTO skill_actions VALUES (?, ?)', (revision + 1, json.dumps(value)))

    def activate(self, identifier, expected):
        with self.service.lock:
            self.check_revision(expected)
            with self.service.connect() as db:
                row = db.execute('SELECT data FROM skill_versions WHERE id=?', (identifier,)).fetchone()
                if not row:
                    raise KeyError('Skill version not found')
                value = json.loads(row[0])
                validate_skill(value['skill'])
                if self.snapshot()['activeVersionId'] != identifier:
                    self.move(db, identifier, expected, 'activate-version')
            return self.snapshot()
