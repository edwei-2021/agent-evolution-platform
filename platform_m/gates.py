"""Acceptance gates stop dependent work and always preserve actionable support bundles."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import queue
import statistics
import threading
import time
import uuid
from .contracts import StepCheck
from .evidence import atomic_write, canonical, digest, redact
from .store import Store

def find_node(root):
    """Resolve the project's Node runtime without assuming scripts/ is importable."""
    scripts = str(Path(root).resolve() / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from setup_wsl import find_node as resolve_node
    return resolve_node(Path(root).resolve())

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

MONITOR_POLICY = 'm-command-watch-v1'
REPORT_INTERVAL_SECONDS = 5
MAX_PROMPT_SECONDS = 30 * 60
MAX_COMMAND_SECONDS = 2 * 60 * 60
FIRST_RUN_SECONDS = {
    'M1': [15, 20], 'M2': [15, 30], 'M3': [30], 'M4': [60, 30],
    'M5': [60], 'M6': [30], 'M7': [90, 30, 30, 900, 60, 60],
}

def prompt_after_seconds(normal):
    return max(normal, min(normal * 10, MAX_PROMPT_SECONDS))

def normal_budget(root, step, command_index):
    """Use recent successful timing for this command, else a conservative estimate."""
    samples = []
    reports = Path(root)/'.local/m/support'
    if reports.is_dir():
        for path in sorted(reports.glob('MCHECK-*/report.json'), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                report = json.loads((path.parent/(step+'.json')).read_text())
            except (OSError, ValueError):
                continue
            if report.get('monitor_policy') != MONITOR_POLICY:
                continue
            if report.get('status') != 'passed':
                continue
            for log in report.get('logs', []):
                if log.get('command_index') == command_index and log.get('exit_code') == 0:
                    elapsed = log.get('elapsed_seconds')
                    if isinstance(elapsed, (int, float)) and elapsed > 0:
                        samples.append(float(elapsed))
                        break
            if len(samples) == 5:
                break
    if samples:
        return max(5, round(statistics.median(samples) * 1.5))
    return FIRST_RUN_SECONDS[step][command_index]

def execute(command, root, environment, timeout=900, normal_seconds=30,
            prompt_after=None, interval=REPORT_INTERVAL_SECONDS, input_fn=None,
            report_overrun=True):
    process = subprocess.Popen(command, cwd=root, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
    lines = queue.Queue()
    end = object()
    def collect():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(end)
    reader = threading.Thread(target=collect, name='m-gate-output', daemon=True)
    reader.start()
    started = time.monotonic()
    prompted = approved = False
    input_fn = input_fn or input
    prompt_after = prompt_after_seconds(normal_seconds) if prompt_after is None else prompt_after
    next_report = started + normal_seconds if report_overrun else started + timeout
    output = []
    def terminate():
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    try:
        stream_done = False
        while not stream_done:
            elapsed = time.monotonic() - started
            deadline = min(started + timeout, next_report,
                           started + prompt_after if not prompted else started + timeout)
            wait = max(0.01, min(0.25, deadline - time.monotonic()))
            try:
                item = lines.get(timeout=wait)
            except queue.Empty:
                item = None
            if item is end:
                stream_done = True
            elif item is not None:
                output.append(item)
                print(redact(item), end='', flush=True)
            now = time.monotonic()
            elapsed = now - started
            overdue = max(0, elapsed - normal_seconds)
            if report_overrun and now >= next_report and overdue:
                print(f'M_CHECK_OVERRUN over_normal_seconds={overdue:.1f} elapsed_seconds={elapsed:.0f} '
                      f'normal_seconds={normal_seconds}', flush=True)
                next_report = now + interval
            if not prompted and elapsed >= prompt_after:
                prompted = True
                print(f'M_CHECK_WAIT_DECISION exceeded_normal_seconds={overdue:.1f}; '
                      'continue waiting? [y/N] ', end='', flush=True)
                try:
                    answer = input_fn().strip().lower()
                except (EOFError, OSError, KeyboardInterrupt):
                    answer = ''
                approved = answer in ('y', 'yes')
                if not approved:
                    terminate()
                    output.append('\nM_CHECK_STOPPED_BY_USER\n')
                    return 125, ''.join(output), {
                        'elapsed_seconds': time.monotonic()-started,
                        'over_normal_seconds': max(0, time.monotonic()-started-normal_seconds),
                        'extension_approved': False, 'stopped_by_user': True,
                        'prompt_after_seconds': prompt_after, 'hard_limit_seconds': timeout}
                print(f'\nM_CHECK_WAIT_APPROVED continuing; over_normal_seconds={overdue:.1f}', flush=True)
                next_report = time.monotonic() + interval
            if elapsed >= timeout and not stream_done:
                terminate()
                output.append('\nM_CHECK_HARD_LIMIT stopping process group\n')
                return 124, ''.join(output), {
                    'elapsed_seconds': time.monotonic()-started,
                    'over_normal_seconds': max(0, time.monotonic()-started-normal_seconds),
                    'extension_approved': approved, 'stopped_by_user': False,
                    'prompt_after_seconds': prompt_after, 'hard_limit_seconds': timeout}
        process.wait()
        elapsed = time.monotonic()-started
        return process.returncode, ''.join(output), {
            'elapsed_seconds': elapsed,
            'over_normal_seconds': max(0, elapsed-normal_seconds),
            'extension_approved': approved, 'stopped_by_user': False,
            'prompt_after_seconds': prompt_after, 'hard_limit_seconds': timeout}
    except KeyboardInterrupt:
        terminate()
        elapsed = time.monotonic()-started
        output.append('\nDBG-INTERRUPTED: process group terminated by Ctrl-C\n')
        return 130, ''.join(output), {
            'elapsed_seconds': elapsed, 'over_normal_seconds': max(0, elapsed-normal_seconds),
            'extension_approved': approved, 'stopped_by_user': True,
            'prompt_after_seconds': prompt_after, 'hard_limit_seconds': timeout}

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
                for index, command in enumerate(commands):
                    normal = normal_budget(self.root, step, index)
                    nested_monitor = 'scripts/check_steps.py' in command
                    prompt_after = MAX_COMMAND_SECONDS + 1 if nested_monitor else prompt_after_seconds(normal)
                    hard_limit = MAX_COMMAND_SECONDS if nested_monitor else min(
                        MAX_COMMAND_SECONDS, max(900, prompt_after + 60))
                    prompt_text = 'managed_by_child' if nested_monitor else str(prompt_after)
                    display = ' '.join(map(str, command[1:])) or str(command[0])
                    print(f'INFO {debug_code} step={step} command={index+1}/{len(commands)} check_started', flush=True)
                    print(f'M_CHECK_EXPECTED step={step} command={index+1}/{len(commands)} '
                          f'normal_seconds={normal} prompt_after_seconds={prompt_text} '
                          f'hard_limit_seconds={hard_limit} argv={display}', flush=True)
                    try:
                        code, output, timing = execute(command, self.root, env,
                            timeout=hard_limit, normal_seconds=normal, prompt_after=prompt_after,
                            report_overrun=not nested_monitor)
                    except (OSError, RuntimeError) as exc:
                        code, output, timing = 127, str(exc), {'elapsed_seconds': 0,
                            'over_normal_seconds': 0, 'extension_approved': False,
                            'stopped_by_user': False, 'prompt_after_seconds': prompt_after,
                            'hard_limit_seconds': hard_limit}
                    logs.append({'command_index': index, 'command': command, 'exit_code': code,
                                 **timing, 'stdout_stderr': redact(output)[-200000:]})
                    if code:
                        status, exit_code, failed = ('blocked' if code == 78 else 'failed'), code, step
                        break
            bundle = self.directory/(step+'.json')
            report = {'step': step, 'status': status, 'debug_code': debug_code,
                      'monitor_policy': MONITOR_POLICY, 'source_hash': self.source_hash,
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
    runtime = find_node(root)
    node = runtime['path'] if runtime else 'node'
    sdk = root/'.venv-nanobot/bin/python'
    # M acceptance runs from /mnt/d on WSL, where pytest's FDCapture tempfiles
    # can disappear during cleanup on DrvFS. The outer gate already captures
    # stdout/stderr into the support bundle, so pytest-level capture is redundant.
    pytest = [python, '-m', 'pytest', '-s']
    return [
        ('M1', [pytest+['tests_m/test_m1.py','-q'], [node,'--test',
            *[str(p.relative_to(root)) for p in sorted((root/'tests').glob('*.test.js'))]]]),
        ('M2', [[python,'scripts/generate_m_contracts.py','--check'],
                pytest+['tests_m/test_m2.py','tests_m/test_nanobot_bridge.py','-q']]),
        ('M3', [pytest+['tests_m/test_m3.py','-q']]),
        ('M4', [[python,'scripts/check_m_environment.py','--docker'],
                pytest+['tests_m/test_m4.py','-q']]),
        ('M5', [pytest+['tests_m/test_m5.py','-q']]),
        ('M6', [pytest+['tests_m/test_m6.py','-q']]),
        ('M7', [pytest+['tests_m/test_m7.py','tests_m/test_gates.py','-q'],
                [python,'scripts/scan_m_source.py'],
                [python,'scripts/check_m_environment.py','--sdk'],
                [str(sdk),'scripts/check_steps.py','--profile','release'],
                [python,'-m','ruff','check','platform_m','tests_m','scripts/generate_m_contracts.py',
                    'scripts/migrate_wsl.py','scripts/check_m.py','scripts/check_m_environment.py','scripts/serve_m.py'],
                [node,'node_modules/typescript/bin/tsc','--noEmit','--strict','--lib','es2020,dom',
                    'packages/contracts/contracts.ts']])]
