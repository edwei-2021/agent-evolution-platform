"""Separate immutable prompt Skills; never mix LLM evidence with rule policy."""
import json
import time
import uuid
from llm_engine import ENGINE, provenance, skill, splits, validate_skill, verify


class LlmStore:
    def __init__(self, service):
        self.service = service
        with service.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS llm_versions (id TEXT PRIMARY KEY, run_id TEXT UNIQUE, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS llm_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, active_id TEXT NOT NULL)')
            version = {'id': 'LSV-baseline', 'label': 'L0', 'parentId': None, 'runId': None,
                       'createdAt': service.timestamp(), 'skill': skill('Return the input unchanged.'), 'evidence': None}
            db.execute('INSERT OR IGNORE INTO llm_versions VALUES (?, NULL, ?)', (version['id'], json.dumps(version)))
            db.execute('INSERT OR IGNORE INTO llm_state VALUES (1, 1, ?)', (version['id'],))

    def snapshot(self):
        with self.service.lock, self.service.connect() as db:
            revision, active_id = db.execute('SELECT revision, active_id FROM llm_state').fetchone()
            versions = [json.loads(r[0]) for r in db.execute('SELECT data FROM llm_versions ORDER BY rowid')]
        return {'schemaVersion': 1, 'engine': ENGINE, 'revision': revision, 'activeVersionId': active_id,
                'active': next(v for v in versions if v['id'] == active_id), 'versions': versions}

    def check_revision(self, expected):
        if type(expected) is not int or expected < 1:
            raise ValueError('expectedRevision must be a positive integer')
        if self.service.closed or self.snapshot()['revision'] != expected:
            raise RuntimeError('LLM Skill state changed or service is stopping; refresh first')

    def freeze(self, options):
        required = {'profile', 'maxSeconds', 'expectedRevision', 'providerRevision'}
        if not isinstance(options, dict) or not required <= set(options) or set(options) - required - {'callTimeoutSeconds'}:
            raise ValueError('Use profile, maxSeconds, expectedRevision, providerRevision and optional callTimeoutSeconds')
        call_timeout = options.get('callTimeoutSeconds', 120)
        if type(call_timeout) is not int or not 10 <= call_timeout <= 3600:
            raise ValueError('callTimeoutSeconds must be an integer between 10 and 3600')
        self.check_revision(options['expectedRevision'])
        if type(options['maxSeconds']) is not int or not 60 <= options['maxSeconds'] <= 7200:
            raise ValueError('maxSeconds must be an integer between 60 and 7200')
        data = splits(options['profile'])
        provider = self.service.ollama.state()
        if type(options['providerRevision']) is not int or options['providerRevision'] != provider['revision']:
            raise RuntimeError('Provider settings changed; refresh first')
        if not provider['config']['model']:
            raise ValueError('Select and save an Ollama model in Integrations first')
        endpoint = self.service.ollama.endpoint(provider['config'])
        budget = 2 * (len(data['train']) + len(data['validation']) + len(data['heldout'])) + 1
        return {'schemaVersion': 1, 'engine': ENGINE, 'profile': options['profile'],
                'baseline': self.snapshot()['active'], 'provider': {**provider, 'endpoint': endpoint},
                'maxSeconds': options['maxSeconds'], 'deadlineEpoch': time.time() + options['maxSeconds'],
                'transport': 'openai-sse-v1', 'callTimeoutSeconds': min(call_timeout, provider['config']['inferenceTimeout']),
                'callBudget': budget, 'maxOutputTokens': budget * provider['config']['maxTokens'],
                'provenance': provenance(options['profile'])}

    def approve(self, identifier, expected):
        with self.service.lock:
            self.check_revision(expected)
            run = self.service.get_run(identifier)
            if run.get('task') != 'llm-evolution' or run['status'] != 'completed' or not run.get('llmResult', {}).get('eligible'):
                raise RuntimeError('Only a completed improving LLM run can be approved')
            directory = self.service.local / 'runs' / identifier
            if json.loads((directory / 'llm-config.json').read_text()) != run['llmConfig']:
                raise ValueError('Frozen LLM configuration was modified')
            result = verify(directory)
            if result != run['llmResult'] or result != json.loads((directory / 'review.json').read_text()):
                raise ValueError('LLM evidence changed after review')
            if run['llmConfig']['baseline']['id'] != self.snapshot()['activeVersionId'] or not result['eligible']:
                raise RuntimeError('Baseline changed or candidate did not improve; start a new run')
            with self.service.connect() as db:
                if db.execute('SELECT id FROM llm_versions WHERE run_id=?', (identifier,)).fetchone():
                    raise RuntimeError('This run already has an approved version')
                count = db.execute('SELECT COUNT(*) FROM llm_versions').fetchone()[0]
                if count >= 100:
                    raise RuntimeError('Local LLM version limit reached (100)')
                value = {'id': 'LSV-' + str(uuid.uuid4()), 'label': f'L{count}', 'parentId': run['llmConfig']['baseline']['id'],
                         'runId': identifier, 'createdAt': self.service.timestamp(), 'skill': result['selectedSkill'],
                         'evidence': result}
                db.execute('INSERT INTO llm_versions VALUES (?, ?, ?)', (value['id'], identifier, json.dumps(value)))
                db.execute('UPDATE llm_state SET revision=?, active_id=?', (expected + 1, value['id']))
            self.service.logs.append('llm', 'INFO', 'Approved model skill version', identifier, {'versionId': value['id'], 'revision': expected + 1})
            return self.snapshot()

    def activate(self, identifier, expected):
        with self.service.lock:
            self.check_revision(expected)
            with self.service.connect() as db:
                row = db.execute('SELECT data FROM llm_versions WHERE id=?', (identifier,)).fetchone()
                if not row:
                    raise KeyError('LLM Skill version not found')
                validate_skill(json.loads(row[0])['skill'])
                if self.snapshot()['activeVersionId'] != identifier:
                    db.execute('UPDATE llm_state SET revision=?, active_id=?', (expected + 1, identifier))
                    self.service.logs.append('llm', 'INFO', 'Activated model skill version', details={'versionId': identifier, 'revision': expected + 1})
            return self.snapshot()
