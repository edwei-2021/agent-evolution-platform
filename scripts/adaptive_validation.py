"""Pre-dispatch validation budgets; production limits are never mutated."""
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import tempfile
import time
from debug_log import DebugLog
from skill_engine import write

ROOT = Path(__file__).resolve().parents[1]
ENV = 'AEP_VALIDATION_CALIBRATION'
MAX_SECONDS = 7200


def calculate(samples, inference_timeout=10):
    if not samples or any(not math.isfinite(v) or v < 0 for v in samples):
        raise ValueError('Invalid filesystem calibration samples')
    if type(inference_timeout) is not int or not 1 <= inference_timeout <= 120:
        raise ValueError('Invalid validation inference timeout')
    # One sample includes one journal transaction and one atomic JSON replace.
    # Four such units cover per-call trace/journal/evidence/progress work;
    # 2x the observed maximum reserves host variability, plus role cleanup.
    io_allowance = max(samples) * 8
    profiles = {}
    from llm_engine import splits
    for profile in ('smoke', 'full'):
        calls = 2 * sum(len(rows) for rows in splits(profile).values()) + 1
        seconds = max(60, math.ceil(calls * (inference_timeout + io_allowance) + 30))
        if seconds > MAX_SECONDS:
            raise ValueError('DBG-ADAPT-001: measured storage cost exceeds the bounded validation budget; inspect filesystem health')
        profiles[profile] = {'calls': calls, 'maxSeconds': seconds}
    return {'schemaVersion': 1, 'policy': 'pre-dispatch workload and filesystem calibration',
            'samplesSeconds': samples, 'perCallIoAllowanceSeconds': io_allowance,
            'inferenceTimeout': inference_timeout, 'profiles': profiles,
            'maximumWorkflowSeconds': MAX_SECONDS, 'modelRequests': 0}


def calibrate(root=ROOT):
    root = Path(root)
    parent = root / '.local/tmp'
    parent.mkdir(parents=True, exist_ok=True)
    samples = []
    with tempfile.TemporaryDirectory(prefix='validation-calibration-', dir=parent) as temporary:
        logs = DebugLog(temporary)
        if not logs.available:
            raise OSError('DBG-ADAPT-002: calibration journal is unavailable')
        logs.keep_open()
        try:
            for index in range(5):
                start = time.monotonic()
                if not logs.append('runtime', 'INFO', 'Validation calibration', details={'sample': index}):
                    raise OSError('DBG-ADAPT-002: calibration journal write failed')
                write(Path(temporary) / 'progress.json', {'sample': index, 'payload': 'x' * 8192})
                samples.append(time.monotonic() - start)
        finally:
            logs.close()
    result = calculate(samples)
    result['filesystemRoot'] = str(parent)
    return result


@lru_cache(maxsize=1)
def current():
    raw = os.environ.get(ENV)
    if raw:
        supplied = json.loads(raw)
        result = calculate(supplied['samplesSeconds'], supplied['inferenceTimeout'])
        result['filesystemRoot'] = supplied.get('filesystemRoot', str(ROOT / '.local/tmp'))
        return result
    result = calibrate()
    target = ROOT / '.local/test-reports'
    target.mkdir(parents=True, exist_ok=True)
    write(target / 'validation-calibration.json', result)
    return result


def workflow_seconds(profile):
    return current()['profiles'][profile]['maxSeconds']


def harness_seconds():
    return workflow_seconds('smoke') + 60
