"""Local Git publication of the signed M release pointer; database remains authoritative."""
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.branch_diagnostics import record
from .evidence import canonical

REF = 'refs/agent-evolution/active'
ZERO = '0' * 40
MAX_MANIFEST = 1_000_000


class ReleaseGit:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _git(self, *args, input=None, missing=False):
        command = ['git', '-C', str(self.root), *args]
        result = subprocess.run(command, input=input, capture_output=True, timeout=10)
        if result.returncode:
            if missing and result.returncode == 1:
                return None
            raise RuntimeError('Local release Git operation failed: ' + args[0])
        return result.stdout.strip() if input is None else result.stdout

    def _check_root(self):
        top = self._git('rev-parse', '--show-toplevel').decode()
        if Path(top).resolve() != self.root:
            raise RuntimeError('Release Git root differs from the configured checkout')
        if self._git('rev-parse', '--show-object-format') != b'sha1':
            raise RuntimeError('Release Git publication requires SHA-1 object format')

    def observed(self):
        """Return the ref object and canonical manifest hash, without writing Git."""
        self._check_root()
        sha = self._git('rev-parse', '--verify', '--quiet', REF, missing=True)
        if sha is None:
            return {'object': ZERO, 'hash': None}
        sha = sha.decode()
        if self._git('cat-file', '-t', sha) != b'blob':
            raise ValueError('Release Git ref must point to a manifest blob')
        size = int(self._git('cat-file', '-s', sha))
        if size > MAX_MANIFEST:
            raise ValueError('Release Git manifest exceeds the read limit')
        raw = self._git('cat-file', 'blob', sha)
        try:
            if canonical(json.loads(raw)) != raw:
                raise ValueError('Release Git manifest is not canonical JSON')
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('Release Git manifest is invalid JSON') from exc
        return {'object': sha, 'hash': hashlib.sha256(raw).hexdigest()}

    def publish(self, identifier, manifest, observed):
        """CAS the ref against the value inspected while holding the DB writer lock."""
        raw = canonical(manifest)
        if len(raw) > MAX_MANIFEST or hashlib.sha256(raw).hexdigest() != identifier:
            raise ValueError('Signed release manifest differs from Git publication')
        record(self.root, 'M6', 'release.git-object-write', 'started',
               manifestBytes=len(raw), hadRef=observed['hash'] is not None)
        sha = self._git('hash-object', '-w', '--stdin', input=raw).strip().decode()
        record(self.root, 'M6', 'release.git-object-write', 'completed',
               manifestBytes=len(raw), sameObject=observed['object'] == sha)
        if observed['object'] == sha:
            return sha
        record(self.root, 'M6', 'release.git-ref-cas', 'started',
               hadRef=observed['hash'] is not None)
        self._git('update-ref', REF, sha, observed['object'])
        record(self.root, 'M6', 'release.git-ref-cas', 'completed')
        return sha
