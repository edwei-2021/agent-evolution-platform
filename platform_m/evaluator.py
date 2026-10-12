"""Digest-pinned Docker evaluator. No host fallback when isolation is requested."""
import json
from pathlib import Path
import re
import shutil
import subprocess
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
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, text=True, timeout=15)
        inspect = subprocess.run(['docker', 'container', 'inspect', name], capture_output=True, text=True, timeout=15)
        cleanup['removed'] = inspect.returncode != 0 and 'No such' in inspect.stderr
        if not cleanup['removed']:
            status, reason = 'invalid_evaluation', 'integrity'
    return {'verdict': status, 'failure_category': reason, 'results': results, 'image': pinned,
            'request_hash': digest(jobs), 'output_hash': digest(output), 'cleanup': cleanup,
            'stderr': error[:4000], 'command': cmd}

def source_hash(root):
    root = Path(root)
    return digest({p.name: __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                   for p in (root/'scripts/repair_fixture.py', root/'scripts/repair_evaluator.py')})
