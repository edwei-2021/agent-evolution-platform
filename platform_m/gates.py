"""Acceptance gates stop dependent work and always preserve actionable support bundles."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid
from .contracts import StepCheck
from .evidence import atomic_write, canonical, digest, redact
from .store import Store

REMEDIATION = {
    'M1': 'Stop GUI/API/worker; inspect migration report, backup integrity and failed regression command.',
    'M2': 'Install locked M dependencies; regenerate contracts; inspect missing fields or schema drift.',
    'M3': 'Inspect SQLite revision, idempotency key, lease/fence, event sequence and worker attempt.',
    'M4': 'Enable Docker Desktop WSL integration; run build-m-images.sh; inspect digest, verdict and cleanup.',
    'M5': 'Inspect split/family/fixture hashes, comparison snapshots, unsafe feedback and per-task regressions.',
    'M6': 'Inspect checkpoint, consumed budget, signature/key permissions, approver role and pointer revision.',
    'M7': 'Install pinned SDKs; inspect API/CI/type/legacy release check output and package/image health.'}

def source_snapshot(root):
    root = Path(root)
    result = subprocess.run(['git','ls-files','--cached','--others','--exclude-standard'], cwd=root,
                            capture_output=True,text=True,timeout=15)
    if result.returncode:
        raise RuntimeError('Git source inventory failed')
    import hashlib
    values = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
              for name in sorted(set(result.stdout.splitlines())) if (root/name).is_file()}
    return digest(values), values

def execute(command, root, environment, timeout=900):
    process = subprocess.Popen(command, cwd=root, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        return 124, output+'\nDBG-TIMEOUT: entire process group terminated\n'

class Gates:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = Store(self.root/'.local/m/control.sqlite3')
        self.source_hash, self.inputs = source_snapshot(self.root)
        self.directory = self.root/'.local/m/support'/('MCHECK-'+uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
    def run(self, plans, environment=None):
        checks, failed = [], None
        env = {**os.environ, **(environment or {})}
        temporary = self.root/'.local/tmp'
        temporary.mkdir(parents=True,exist_ok=True)
        env.update(TMPDIR=str(temporary),TMP=str(temporary),TEMP=str(temporary),
                   TIKTOKEN_CACHE_DIR=str(self.root/'.local/cache/tiktoken'))
        for step, commands in plans:
            started = time.time()
            debug_code = 'DBG-M-'+step[1:].zfill(3)
            status, exit_code, logs = 'passed', 0, []
            if failed:
                status, exit_code = 'blocked', 2
                logs.append({'blocked_by': failed, 'command_executed': False})
            else:
                for command in commands:
                    print(f'INFO {debug_code} step={step} check_started', flush=True)
                    try:
                        code, output = execute(command, self.root, env)
                    except (OSError, RuntimeError) as exc:
                        code, output = 127, str(exc)
                    logs.append({'command': command, 'exit_code': code, 'stdout_stderr': redact(output)[-200000:]})
                    if code:
                        status, exit_code, failed = ('blocked' if code == 78 else 'failed'), code, step
                        break
            bundle = self.directory/(step+'.json')
            report = {'step': step, 'status': status, 'debug_code': debug_code, 'source_hash': self.source_hash,
                      'input_hashes': self.inputs, 'logs': logs, 'blocked_by': failed if status == 'blocked' else None,
                      'python': sys.version, 'remediation': REMEDIATION[step]}
            atomic_write(bundle, canonical(redact(report)))
            row = StepCheck(id=uuid.uuid4().hex, step=step, status=status, debug_code=debug_code,
                source_hash=self.source_hash, input_hash=digest(self.inputs), started_at=started,
                finished_at=time.time(), command=commands[0] if commands else [], exit_code=exit_code,
                bundle=str(bundle.relative_to(self.root)), remediation=REMEDIATION[step])
            self.store.check(row.model_dump())
            checks.append(row.model_dump())
            print(f'{"INFO" if status == "passed" else "ERROR"} {debug_code} step={step} status={status} '
                  f'bundle={bundle.relative_to(self.root)}', flush=True)
        result = {'phase': 'M', 'status': 'passed' if failed is None else 'blocked',
                  'source_hash': self.source_hash, 'checks': checks, 'finished_at': time.time()}
        atomic_write(self.directory/'report.json', canonical(result))
        print('Support report: '+str(self.directory/'report.json'), flush=True)
        return result

def plans(root, python):
    root = Path(root)
    node = shutil.which('node') or 'node'
    sdk = root/'.venv-nanobot/bin/python'
    return [
        ('M1', [[python,'-m','pytest','tests_m/test_m1.py','-q'], [node,'--test',
            *[str(p.relative_to(root)) for p in sorted((root/'tests').glob('*.test.js'))]]]),
        ('M2', [[python,'scripts/generate_m_contracts.py','--check'],
                [python,'-m','pytest','tests_m/test_m2.py','tests_m/test_nanobot_bridge.py','-q']]),
        ('M3', [[python,'-m','pytest','tests_m/test_m3.py','-q']]),
        ('M4', [[python,'scripts/check_m_environment.py','--docker'],
                [python,'-m','pytest','tests_m/test_m4.py','-q']]),
        ('M5', [[python,'-m','pytest','tests_m/test_m5.py','-q']]),
        ('M6', [[python,'-m','pytest','tests_m/test_m6.py','-q']]),
        ('M7', [[python,'-m','pytest','tests_m/test_m7.py','tests_m/test_gates.py','-q'],
                [python,'scripts/scan_m_source.py'],
                [python,'scripts/check_m_environment.py','--sdk'],
                [str(sdk),'scripts/check_steps.py','--profile','release'],
                [python,'-m','ruff','check','platform_m','tests_m','scripts/generate_m_contracts.py',
                    'scripts/migrate_wsl.py','scripts/check_m.py','scripts/check_m_environment.py','scripts/serve_m.py'],
                [node,'node_modules/typescript/bin/tsc','--noEmit','--strict','--lib','es2020,dom',
                    'packages/contracts/contracts.ts']])]
