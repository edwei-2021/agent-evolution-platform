"""Isolated, observable package probes; no model requests or automatic retries."""
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import time
import threading

PROBE_SECONDS = 120
PROBE_INTERVAL = 10
PREFIX = 'AEP_SDK_PROBE '
_observed = {}
_observation_lock = threading.Lock()

PROGRAM = r'''
import importlib, importlib.metadata, json, sys, traceback
distribution, module, required, symbol = sys.argv[1:]
def emit(**data):
    print('AEP_SDK_PROBE ' + json.dumps(data), flush=True)
emit(stage='metadata', python=sys.executable)
try:
    version = importlib.metadata.version(distribution)
except importlib.metadata.PackageNotFoundError:
    emit(stage='metadata', errorCode='missing_package')
    raise SystemExit(2)
emit(stage='metadata', version=version)
if version != required:
    emit(stage='metadata', version=version, errorCode='version_mismatch')
    raise SystemExit(2)
emit(stage='import', version=version)
try:
    package = importlib.import_module(module)
    if symbol:
        getattr(package, symbol)
except Exception:
    traceback.print_exc()
    emit(stage='import', version=version, errorCode='import_error')
    raise SystemExit(2)
emit(stage='complete', version=version, available=True)
'''


def _events(stdout):
    latest = {}
    for line in stdout.splitlines():
        if line.startswith(PREFIX):
            try:
                event = json.loads(line[len(PREFIX):])
                if isinstance(event, dict):
                    latest.update(event)
            except ValueError:
                pass
    return latest


def probe(executable, distribution, module, required, symbol='', *, seconds=PROBE_SECONDS,
          interval=PROBE_INTERVAL):
    """One child and one absolute deadline, shared by metadata and import."""
    if not math.isfinite(seconds) or seconds <= 0 or not math.isfinite(interval) or interval <= 0:
        raise ValueError('Invalid SDK probe deadline')
    command = [str(executable), '-I', '-u', '-X', 'importtime', '-c', PROGRAM, distribution, module, required, symbol]
    started = time.monotonic()
    from diagnostic_log import DiagnosticLog
    diagnostics = DiagnosticLog()
    diagnostics.write('sdk', 'probe.started', package=distribution, python=str(executable),
                      requiredVersion=required, timeoutSeconds=seconds, modelRequests=0)
    stdout = stderr = ''
    status = {'available': False, 'version': None, 'requiredVersion': required,
              'python': str(executable), 'error': None, 'errorCode': None}
    print(f'SDK_PROBE_STARTED package={distribution} python={executable} '
          f'maximum_seconds={seconds} model_requests=0', flush=True)
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    except OSError as exc:
        status.update(errorCode='launch_error', error=str(exc))
        process = None
    if process is not None:
        try:
            while True:
                remaining = seconds - (time.monotonic() - started)
                if remaining <= 0:
                    status['errorCode'] = 'probe_timeout'
                    process.kill()
                    stdout, stderr = process.communicate()
                    break
                try:
                    stdout, stderr = process.communicate(timeout=min(interval, remaining))
                    break
                except subprocess.TimeoutExpired as exc:
                    partial = exc.stdout or b''
                    if isinstance(partial, bytes):
                        partial = partial.decode('utf-8', errors='replace')
                    stage = _events(partial).get('stage', 'interpreter-startup')
                    diagnostics.write('sdk', 'probe.waiting', package=distribution, stage=stage,
                                      elapsedSeconds=round(time.monotonic()-started,3), timeoutSeconds=seconds)
                    print(f'SDK_PROBE_WAIT package={distribution} stage={stage} '
                          f'elapsed_seconds={time.monotonic()-started:.1f} maximum_seconds={seconds}',
                          flush=True)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        event = _events(stdout)
        status['version'] = event.get('version')
        if not status['errorCode']:
            status['available'] = (process.returncode == 0 and event.get('available') is True
                                   and status['version'] == required and event.get('stage') == 'complete')
            if not status['available']:
                status['errorCode'] = event.get('errorCode') or (
                    'process_error' if process.returncode else 'invalid_output')
        status['probe'] = {'stage': event.get('stage', 'interpreter-startup'),
                           'exitCode': process.returncode, 'stdout': stdout[-8000:], 'stderr': stderr[-8000:]}
    else:
        status['probe'] = {'stage': 'interpreter-startup', 'exitCode': None, 'stdout': '', 'stderr': ''}
    status['probe'].update(elapsedSeconds=round(time.monotonic()-started, 3),
                           timeoutSeconds=seconds, modelRequests=0,
                           command=[str(executable), '-I', '-u', '-X', 'importtime', '-c', '<package-probe>',
                                    distribution, module, required, symbol])
    if status['errorCode']:
        status['error'] = (f'{distribution} probe failed: {status["errorCode"]}; '
                           f'stage={status["probe"]["stage"]}; python={executable}; '
                           f'installed={status["version"]}; required={required}; '
                           f'elapsed={status["probe"]["elapsedSeconds"]}s. '
                           'Inspect probe diagnostics before reinstalling.') + (
                               ' ' + str(status['error']) if status['error'] else '')
    summary = {key: value for key, value in status.items() if key != 'probe'}
    summary.update(stage=status['probe']['stage'], elapsedSeconds=status['probe']['elapsedSeconds'],
                   timeoutSeconds=seconds)
    print('SDK_PROBE_RESULT ' + json.dumps(summary, ensure_ascii=False), flush=True)
    diagnostics.write('sdk', 'probe.finished', level='INFO' if status['available'] else 'ERROR',
                      package=distribution, **summary, exitCode=status['probe']['exitCode'], stderrTail=stderr[-900:])
    if not status['available']:
        print('SDK_PROBE_DIAGNOSTICS ' + json.dumps(status['probe'], ensure_ascii=False), flush=True)
    return status


class _UnsuccessfulProbe(Exception):
    def __init__(self, status):
        self.status = status


@lru_cache(maxsize=16)
def _successful_probe(executable, distribution, module, required, symbol, marker, time_window):
    status = probe(executable, distribution, module, required, symbol)
    if not status['available']:
        # lru_cache never stores exceptions: a transient timeout cannot poison
        # every later call until the interpreter file happens to change.
        raise _UnsuccessfulProbe(status)
    return json.dumps(status)


def package_status(executable, distribution, module, required, symbol='', marker=0, *, cached_only=False):
    try:
        stamp = Path(executable).stat().st_mtime_ns
    except OSError:
        stamp = 0
    key = (str(executable), distribution, module, required, symbol, (marker, stamp),
           int(time.monotonic() // 300))
    if cached_only:
        with _observation_lock:
            observed = _observed.get(key)
        if observed is not None:
            return json.loads(observed)
        return {'available': False, 'version': None, 'requiredVersion': required,
                'python': str(executable), 'errorCode': 'not_probed',
                'error': 'SDK discovery is pending; availability is not yet confirmed'}
    try:
        result = _successful_probe(*key)
        # Read-only API observations never start an interpreter. This cache
        # has the same executable/marker/time-window identity as the probe.
        with _observation_lock:
            if len(_observed) >= 16:
                _observed.pop(next(iter(_observed)))
            _observed[key] = result
        return json.loads(result)
    except _UnsuccessfulProbe as exc:
        with _observation_lock:
            if len(_observed) >= 16:
                _observed.pop(next(iter(_observed)))
            _observed[key] = json.dumps(exc.status)
        return exc.status
