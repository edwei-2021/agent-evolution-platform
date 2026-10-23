"""One unattended Phase M matrix job owned by the local GUI service."""
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_m.evidence import atomic_write, canonical, redact


def now():
    return datetime.now(timezone.utc).isoformat()


class MatrixService:
    def __init__(self, root, command_factory=None):
        self.root = Path(root).resolve()
        self.directory = self.root/'.local/m/matrix-control'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.command_factory = command_factory or self.default_command
        self.process = None
        self.thread = None
        self.active = None
        self.cancelled = threading.Event()
        self.closed = False
        # A service restart cannot claim an abandoned matrix was completed.
        for path in self.directory.glob('MAT-*.json'):
            try:
                row = json.loads(path.read_text())
                if row['status'] in ('queued', 'running', 'cancelling'):
                    row.update(status='interrupted', finishedAt=now(), error='GUI service restarted; prior process state is unconfirmed')
                    atomic_write(path, canonical(row))
            except (OSError, ValueError, KeyError):
                continue

    def default_command(self, output):
        python = self.root/'.venv-m/bin/python'
        return [str(python), str(self.root/'scripts/check_m_matrix.py'), '--prepare-docker',
                '--output', str(output)]

    def job_path(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 36 or not identifier.startswith('MAT-') or any(
                c not in '0123456789abcdef' for c in identifier[4:]):
            raise KeyError('Matrix job not found')
        return self.directory/(identifier+'.json')

    def save(self, job):
        atomic_write(self.job_path(job['id']), canonical(job))

    def start(self):
        with self.lock:
            if self.closed:
                raise RuntimeError('GUI service is closing')
            if self.active is not None:
                raise RuntimeError('A matrix is already running')
            identifier = 'MAT-'+uuid.uuid4().hex
            output = self.root/'.local/m/matrix'/('MATRIX-'+uuid.uuid4().hex)
            command = self.command_factory(output)
            job = {'id': identifier, 'status': 'queued', 'createdAt': now(),
                   'output': str(output.relative_to(self.root)), 'command': command,
                   'roundsRequired': 3, 'exitCode': None}
            self.save(job)
            self.active = identifier
            self.cancelled.clear()
            self.thread = threading.Thread(target=self.run, args=(job, command, output), daemon=True,
                                           name='phase-m-matrix')
            self.thread.start()
            return self.snapshot(identifier)

    def run(self, job, command, output):
        tail = deque(maxlen=4096)
        last_save = 0.0
        try:
            with self.lock:
                if self.cancelled.is_set():
                    raise InterruptedError('Cancelled before process startup')
                process = subprocess.Popen(command, cwd=self.root, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
                self.process = process
                job.update(status='running', startedAt=now(), pid=process.pid)
                self.save(job)
            for line in process.stdout:
                tail.append(redact(line))
                if time.monotonic() - last_save >= 2:
                    atomic_write(self.directory/(job['id']+'.log'), ''.join(tail)[-262144:].encode())
                    last_save = time.monotonic()
            code = process.wait()
            summary_path = output/'summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
            job.update(status='cancelled' if self.cancelled.is_set() else
                       'completed' if code == 0 and summary.get('status') == 'passed' else 'failed',
                       exitCode=code, finishedAt=now())
            if job['status'] == 'failed':
                job['error'] = 'Matrix did not pass; inspect summary and first failed attempt'
        except BaseException as exc:
            job.update(status='cancelled' if self.cancelled.is_set() else 'failed',
                       error=redact(str(exc))[:300], finishedAt=now())
        finally:
            log = self.directory/(job['id']+'.log')
            atomic_write(log, ''.join(tail)[-262144:].encode())
            if not (output/'support.zip').is_file():
                output.mkdir(parents=True, exist_ok=True)
                summary = output/'summary.json'
                if not summary.is_file():
                    atomic_write(summary, canonical({'status': 'incomplete', 'error': job.get('error'),
                        'coverage': {'flowPasses': {flow: 0 for flow in
                                                   ('configurations', 'other-options', 'components', 'acceptance')},
                                     'expectedPerFlow': 3,
                                     'unexecuted': [{'flow': flow, 'round': number}
                                                    for flow in ('configurations', 'other-options', 'components', 'acceptance')
                                                    for number in (1, 2, 3)]}}))
                with zipfile.ZipFile(output/'support.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('job.json', canonical(job))
                    archive.write(log, 'runner.log')
                    archive.write(summary, 'summary.json')
                    if (output/'events.jsonl').is_file():
                        archive.write(output/'events.jsonl', 'events.jsonl')
            with self.lock:
                self.save(job)
                self.process = None
                self.active = None

    def snapshot(self, identifier):
        job = json.loads(self.job_path(identifier).read_text())
        output = self.root/job['output']
        summary_path = output/'summary.json'
        if summary_path.is_file() and not summary_path.is_symlink() and summary_path.stat().st_size <= 2_000_000:
            job['summary'] = json.loads(summary_path.read_text())
        events = output/'events.jsonl'
        if events.is_file() and not events.is_symlink():
            with events.open('rb') as stream:
                stream.seek(max(0, events.stat().st_size - 65536))
                job['eventsTail'] = stream.read().decode(errors='replace').splitlines()[-20:]
        log = self.directory/(identifier+'.log')
        if log.is_file() and not log.is_symlink():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 12000))
                job['logTail'] = stream.read().decode(errors='replace')
        job['archiveReady'] = (output/'support.zip').is_file() and job['status'] in ('completed', 'failed', 'cancelled', 'interrupted')
        return job

    def list(self):
        paths = sorted(self.directory.glob('MAT-*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
        return {'jobs': [json.loads(path.read_text()) for path in paths[:10]]}

    def archive(self, identifier):
        job = self.snapshot(identifier)
        path = (self.root/job['output']/'support.zip').resolve()
        if not job['archiveReady'] or not path.is_relative_to((self.root/'.local/m/matrix').resolve()):
            raise KeyError('Matrix archive is not ready')
        return path

    def cancel(self, identifier):
        with self.lock:
            if self.active != identifier:
                raise RuntimeError('This matrix is not active')
            self.cancelled.set()
            job = json.loads(self.job_path(identifier).read_text())
            job['status'] = 'cancelling'
            self.save(job)
            if self.process is not None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            return self.snapshot(identifier)

    def close(self):
        with self.lock:
            self.closed = True
            active = self.active
        if active:
            try:
                self.cancel(active)
            except RuntimeError:
                pass
            self.thread.join(timeout=70)
            if self.thread.is_alive():
                with self.lock:
                    if self.process is not None:
                        try:
                            os.killpg(self.process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                self.thread.join(timeout=5)
