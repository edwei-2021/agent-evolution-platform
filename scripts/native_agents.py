#!/usr/bin/env python3
"""Fixed, real tool-agent tasks. No LLM, nanobot or GEPA execution."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def execute(argv, cwd, output):
    print('Executing: ' + ' '.join(map(str, argv)), flush=True)
    with output.open('w') as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=90)
    text = output.read_text(errors='replace')
    print(text[-8000:], flush=True)
    return {'exitCode': result.returncode, 'command': list(map(str, argv)), 'output': output.name}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=['coordinator', 'worker', 'evaluator', 'reflector', 'reviewer'])
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    if args.role == 'coordinator':
        files = sorted(p for p in (ROOT / 'dist').rglob('*') if p.is_file())
        manifest = [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
        if not any(f['path'] == 'dist/index.html' for f in manifest):
            raise RuntimeError('GUI entry is missing')
        write(run_dir / 'manifest.json', {'task': 'project-health', 'files': manifest, 'agentConfig': 'agents.json'})
        print(f'Inspected {len(files)} assets and saved SHA-256 manifest.', flush=True)
    elif args.role == 'worker':
        from setup_wsl import find_node
        node = find_node()
        if not node:
            raise RuntimeError('Supported Linux Node is unavailable; run install-wsl.sh')
        result = execute([node['path'], '--test', *map(str, sorted((ROOT / 'tests').glob('*.test.js')))], ROOT, run_dir / 'javascript-tests.log')
        write(run_dir / 'worker-result.json', result)
        # Test failure is recorded evidence; the downstream reviewer must inspect it.
    elif args.role == 'evaluator':
        # Include installer and skill regressions; exclude runtime_test.py to avoid recursion.
        result = execute([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 's*_test.py'], ROOT, run_dir / 'python-tests.log')
        write(run_dir / 'evaluator-result.json', result)
    elif args.role == 'reflector':
        evidence = {role: json.loads((run_dir / filename).read_text()) for role, filename in [('worker', 'worker-result.json'), ('evaluator', 'evaluator-result.json')]}
        failed = [role for role, value in evidence.items() if value['exitCode'] != 0]
        recommendations = ['Inspect failed test logs and reproduce the failure before editing.'] if failed else ['Keep the verified baseline; no repair is justified by these checks.']
        write(run_dir / 'reflection.json', {'method': 'rule-based evidence analysis; not GEPA', 'failedStages': failed, 'recommendations': recommendations, 'skillChanged': False})
        print('Analyzed actual test exit codes. ' + recommendations[0], flush=True)
    elif args.role == 'reviewer':
        reflection = json.loads((run_dir / 'reflection.json').read_text())
        artifacts = [p for p in run_dir.iterdir() if p.suffix == '.json' and p.name != 'review.json']
        write(run_dir / 'review.json', {'checksPassed': not reflection['failedStages'], 'decision': 'checks-passed' if not reflection['failedStages'] else 'changes-required', 'published': False, 'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}})
        print('Review saved; no Skill or Git release was published.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
