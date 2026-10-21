"""Evidence-derived immutable manifests, Ed25519 approval and transactional pointers."""
from scripts.branch_diagnostics import diagnosed
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from .contracts import Release
from .dataset import compare
from .evidence import canonical

def signing_key_path(root):
    """Return a private-key path on Linux state storage by default.

    Existing project-local keys remain authoritative so their signatures are
    preserved. A path can be selected explicitly via AEP_SIGNING_KEY_PATH.
    """
    configured = os.environ.get('AEP_SIGNING_KEY_PATH')
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(root).resolve()
    legacy = root/'.local/m/signing.key'
    if legacy.exists() or legacy.is_symlink():
        return legacy
    state_home = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state')).expanduser()
    project_id = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return state_home/'agent-evolution-platform'/project_id/'signing.key'

class Releases:
    def __init__(self, store, artifacts, key_path, allow_test_evidence=False):
        self.store, self.artifacts, self.key_path = store, artifacts, Path(key_path)
        self.allow_test_evidence = allow_test_evidence
    def init_key(self):
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw, serialization.NoEncryption())
        fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
    def _key(self):
        if self.key_path.is_symlink() or self.key_path.stat().st_mode & 0o077:
            raise RuntimeError('Signing key requires owner-only permissions')
        return Ed25519PrivateKey.from_private_bytes(self.key_path.read_bytes())
    @diagnosed('M6','release.register')
    def register(self, manifest):
        release = Release.model_validate(manifest).model_dump()
        for name in ('skill_hash', 'workflow_hash', 'runtime_hash', 'model_policy_hash', 'tool_policy_hash',
                     'evaluator_hash', 'dataset_hash', 'memory_snapshot_hash'):
            self.artifacts.get(release[name])
        for value in release['fixture_hashes']:
            self.artifacts.get(value)
        with self.store.db() as db:
            evaluations = []
            observed = {'baseline':set(), 'candidate':set()}
            for identifier in release['result_ids']:
                row = db.execute('SELECT data FROM evaluations WHERE id=?', (identifier,)).fetchone()
                if not row:
                    raise ValueError('Unknown trusted evaluation')
                value = json.loads(row[0])
                for artifact in value['artifacts']:
                    self.artifacts.get(artifact)
                if not self.allow_test_evidence:
                    observed[value['label']].add(self.replay(value, release))
                evaluations.append(value)
        if not self.allow_test_evidence and (any(len(v) != 1 for v in observed.values()) or
                observed['baseline'] == observed['candidate']):
            raise ValueError('Comparison must use one fixed, changed candidate Skill')
        report = compare([v for v in evaluations if v['split'] == 'independent_test'],
                         self.artifacts.get(release['dataset_hash']))
        validation = [v for v in evaluations if v['split'] == 'validation']
        expected_tasks = {t['id'] for t in self.artifacts.get(release['dataset_hash'])['tasks']
                          if t['split'] == 'validation'}
        expected = {(label, task) for label in ('baseline','candidate') for task in expected_tasks}
        pairs = [(v['label'],v['task_id']) for v in validation]
        if len(set(pairs)) != len(pairs) or set(pairs) != expected or any(
                v['verdict'] == 'invalid_evaluation' or v['repetition'] != 0 or
                v['dataset_hash'] != release['dataset_hash'] or v['evaluator_hash'] != release['evaluator_hash'] or
                v['snapshot_hash'] != report['snapshot_hash'] for v in validation):
            raise ValueError('Complete matching validation evidence required')
        totals = {label: sum(v['score'] for v in validation if v['label'] == label) for label in ('baseline','candidate')}
        if totals['candidate'] <= totals['baseline']:
            raise ValueError('Validation did not improve; retain baseline')
        validation_scores = {(v['label'],v['task_id']):v['score'] for v in validation}
        report['validation_regressions'] = sorted(task for task in expected_tasks
            if validation_scores['baseline',task] == 1 and validation_scores['candidate',task] == 0)
        if report['validation_regressions']:
            raise ValueError('Validation lost baseline successes; retain baseline')
        report['validation_totals'] = totals
        report['result_ids'] = sorted(release['result_ids'])
        if not report['eligible'] or report['evaluator_hash'] != release['evaluator_hash']:
            raise ValueError('Release withheld: no improvement or regression/evaluator mismatch')
        data = self.artifacts.get(release['dataset_hash'])
        if sorted(release['fixture_hashes']) != sorted(t['fixture_hash'] for t in data['tasks']):
            raise ValueError('Release fixture manifest mismatch')
        comparison_hash = self.artifacts.put(report)
        identifier = self.artifacts.put(release)
        with self.store.db() as db:
            db.execute('INSERT OR IGNORE INTO releases VALUES(?,?,?)', (identifier, canonical(release).decode(), comparison_hash))
        return identifier
    @diagnosed('M6','release.replay')
    def replay(self, value, release):
        # Recompute task success from frozen source/fixture in the same protected image.
        from .evaluator import evaluate
        descriptor = self.artifacts.get(release['evaluator_hash'])
        dataset = self.artifacts.get(release['dataset_hash'])
        task = next((t for t in dataset['tasks'] if t['id'] == value['task_id']), None)
        if not task or task['split'] != value['split'] or len(value['artifacts']) != 2:
            raise ValueError('Evaluation task/evidence mismatch')
        execution = self.artifacts.get(value['artifacts'][0])
        if execution.get('status') != 'succeeded' or execution.get('task_id') != value['task_id']:
            raise ValueError('Verified execution required before release')
        parent=execution.get('output',{}).get('canonical_job_id',execution.get('run_id'))
        with self.store.db() as db:
            committed=db.execute("SELECT r.data FROM results r JOIN jobs j ON j.id=r.job_id "
                "WHERE j.id=? AND j.state='completed'",(parent,)).fetchone()
        if not committed or execution.get('run_id')!=value['run_id']:
            raise ValueError('Committed completed execution required before release')
        final=json.loads(committed[0])
        if parent==value['run_id'] and (final.get('evaluation')!=value or final.get('execution')!=execution):
            raise ValueError('Release evaluation differs from committed execution')
        if parent!=value['run_id'] and not any(e['type']=='rollout.committed' and
                e['payload'].get('execution_hash')==value['artifacts'][0]
                for e in self.store.events(parent,limit=500)):
            raise ValueError('Rollout is absent from committed parent evidence')
        loaded = execution['loaded_skill_hash']
        self.artifacts.get(loaded)
        if value['label'] == 'candidate' and loaded != release['skill_hash']:
            raise ValueError('Candidate Skill differs from release Skill')
        report = evaluate([{'source':execution['output']['candidate_source'],'split':'hidden',
                            'fixture':self.artifacts.get(task['fixture_hash'])}],descriptor['image'])
        expected = 'pass' if value['score'] == 1 else 'fail'
        if report['verdict'] != expected or not report['cleanup']['removed']:
            raise ValueError('Fresh evaluator replay differs from stored verdict')
        return loaded
    @diagnosed('M6','release.approve')
    def approve(self, identifier, actor, role, rationale):
        if role != 'approver' or not actor or not rationale.strip():
            raise PermissionError('Approver identity and rationale required')
        with self.store.db() as db:
            row = db.execute('SELECT data FROM releases WHERE hash=?', (identifier,)).fetchone()
            if not row:
                raise KeyError(identifier)
            manifest = json.loads(row[0])
            if self.artifacts.get(identifier) != manifest:
                raise ValueError('Manifest integrity failure')
            key = self._key()
            public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            signature = base64.b64encode(key.sign(canonical(manifest))).decode()
            db.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?)', (identifier, actor, time.time(), rationale,
                        signature, base64.b64encode(public).decode()))
            self.store._event(db, identifier, 'approved', {'actor': actor, 'rationale': rationale})
    @diagnosed('M6','release.verify')
    def verify(self, identifier, db):
        row = db.execute('SELECT r.data,a.signature,a.public_key FROM releases r JOIN approvals a ON a.hash=r.hash WHERE r.hash=?',
                         (identifier,)).fetchone()
        if not row:
            raise ValueError('Unapproved manifest')
        manifest = json.loads(row['data'])
        if self.artifacts.get(identifier) != manifest:
            raise ValueError('Manifest checksum mismatch')
        public = self._key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if public != base64.b64decode(row['public_key']):
            raise ValueError('Untrusted signing key')
        Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(row['signature']), canonical(manifest))
        for name in ('skill_hash', 'workflow_hash', 'runtime_hash', 'model_policy_hash', 'tool_policy_hash',
                     'evaluator_hash', 'dataset_hash', 'memory_snapshot_hash'):
            self.artifacts.get(manifest[name])
        for h in manifest['fixture_hashes']:
            self.artifacts.get(h)
        return manifest
    def active(self):
        with self.store.db() as db:
            return dict(db.execute('SELECT hash,revision FROM active').fetchone())
    @diagnosed('M6','release.activate')
    def activate(self, identifier, expected_revision, actor, role, rollback=False):
        if role != 'approver' or not actor:
            raise PermissionError('Only approver may activate')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute('SELECT * FROM active').fetchone()
            if active['revision'] != expected_revision:
                raise RuntimeError('Active pointer changed; refresh')
            manifest = self.verify(identifier, db)
            if not rollback and manifest['parent_release'] != active['hash']:
                raise ValueError('Parent release no longer active')
            if rollback:
                if not active['hash'] or self.verify(active['hash'], db)['parent_release'] != identifier:
                    raise ValueError('Rollback must target active release parent')
            db.execute('UPDATE active SET hash=?,revision=revision+1 WHERE singleton=1', (identifier,))
            self.store._event(db, identifier, 'rollback' if rollback else 'activated',
                              {'actor': actor, 'previous': active['hash'], 'revision': expected_revision+1})
        return self.active()
