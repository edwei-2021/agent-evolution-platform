"""Digest-pinned Docker evaluator. No host fallback when isolation is requested."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from .evidence import digest

def image_id(image):
    if not shutil.which('docker'):
        raise RuntimeError('DBG-M-004 Docker CLI missing; enable Docker Desktop WSL integration')
    result = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image],
                            text=True, capture_output=True, timeout=15)
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r'sha256:[a-f0-9]{64}', value):
        raise RuntimeError('DBG-M-004 immutable evaluator image missing; run build-m-images.sh')
    return value

def command(image, name):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image) or not re.fullmatch(r'meval-[a-f0-9]{32}', name):
        raise ValueError('Digest-pinned image and safe container name required')
    return ['docker', 'run', '--name', name, '--rm', '--pull=never', '-i', '--network=none', '--read-only',
            '--user=65534:65534', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=32',
            '--memory=256m', '--memory-swap=256m', '--cpus=1', '--tmpfs=/tmp:rw,noexec,nosuid,size=16m',
            '--label=aep.phase=M4', image]

def cleanup_container(name, timeout=5):
    """Remove an evaluator container and verify removal with bounded retries."""
    deadline = time.monotonic() + timeout
    result = {'container': name, 'removed': False, 'remove_exit_code': None,
              'remove_stderr': '', 'inspect_exit_code': None, 'inspect_stderr': '',
              'last_state': None}
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            removed = subprocess.run(['docker', 'rm', '-f', name], capture_output=True,
                                     text=True, timeout=min(3, remaining))
            result['remove_exit_code'] = removed.returncode
            result['remove_stderr'] = removed.stderr[:1000]
        except (OSError, subprocess.TimeoutExpired) as exc:
            result['remove_stderr'] = str(exc)[:1000]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            inspected = subprocess.run(['docker', 'container', 'inspect', '--format', '{{.State.Status}}', name],
                                       capture_output=True, text=True, timeout=min(3, remaining))
            result['inspect_exit_code'] = inspected.returncode
            result['inspect_stderr'] = inspected.stderr[:1000]
            result['last_state'] = inspected.stdout.strip() or None
            error = inspected.stderr.lower()
            if inspected.returncode != 0 and ('no such' in error or 'not found' in error):
                result['removed'] = True
                break
        except (OSError, subprocess.TimeoutExpired) as exc:
            result['inspect_stderr'] = str(exc)[:1000]
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.25, remaining))
    return result

def evaluate(jobs, image, timeout=10):
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 32:
        raise ValueError('Use 1..32 evaluator jobs')
    payload = json.dumps({'jobs': jobs})
    if len(payload.encode()) > 1000000:
        raise ValueError('Evaluator input exceeds 1 MB')
    pinned = image_id(image)
    name = 'meval-' + uuid.uuid4().hex
    cmd = command(pinned, name)
    cleanup = {'container': name, 'removed': False}
    output, error = '', ''
    status = 'invalid_evaluation'
    reason = 'infrastructure'
    results = []
    try:
        completed = subprocess.run(cmd, input=payload, text=True, capture_output=True, timeout=timeout)
        output, error = completed.stdout, completed.stderr
        data = json.loads(output)
        if completed.returncode == 0 and isinstance(data.get('results'), list) and len(data['results']) == len(jobs):
            results = data['results']
            if any(type(r.get('passed')) is not int or type(r.get('total')) is not int or
                   not 0 <= r['passed'] <= r['total'] or r['total'] < 1 for r in results):
                raise ValueError('Malformed evaluator evidence')
            status, reason = ('pass','none') if all(r['passed'] == r['total'] for r in results) else ('fail','assertion')
        elif data.get('error'):
            # Policy-rejected candidate is a valid zero; malformed infrastructure is invalid.
            from scripts.repair_fixture import validate_source
            try:
                for job in jobs:
                    validate_source(job['source'])
            except (ValueError, SyntaxError):
                status, reason = 'fail', 'policy'
    except subprocess.TimeoutExpired:
        status, reason = 'fail', 'timeout'
    except (OSError, ValueError):
        status, reason = 'invalid_evaluation', 'infrastructure'
    finally:
        evaluation_status, evaluation_reason = status, reason
        cleanup = cleanup_container(name)
        if not cleanup['removed']:
            status, reason = 'invalid_evaluation', 'integrity'
    return {'verdict': status, 'failure_category': reason, 'results': results, 'image': pinned,
            'evaluation_verdict': evaluation_status, 'evaluation_failure_category': evaluation_reason,
            'request_hash': digest(jobs), 'output_hash': digest(output), 'cleanup': cleanup,
            'stderr': error[:4000], 'command': cmd}

def source_hash(root):
    root = Path(root)
    return digest({p.name: __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                   for p in (root/'scripts/repair_fixture.py', root/'scripts/repair_evaluator.py')})
