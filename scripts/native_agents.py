#!/usr/bin/env python3
"""Fixed, real tool-agent tasks. No LLM, nanobot or GEPA execution."""
import argparse
import hashlib
import json
import subprocess
import os
import signal
import sys
from pathlib import Path
from native_check_plan import CHILD_CLEANUP_SECONDS

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def execute(argv, cwd, output, *, normal, maximum, calibration):
    from check_steps import supervise
    from adaptive_validation import ENV
    print('Executing: ' + ' '.join(map(str, argv)), flush=True)
    with output.open('w') as stream:
        process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True,
                                   env={**os.environ, ENV: json.dumps(calibration)})
        result = supervise(process, output.stem, normal, maximum, output_path=stream, interactive=False,
                           cleanup_seconds=CHILD_CLEANUP_SECONDS)
    return {**result, 'command': list(map(str, argv)), 'output': output.name}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=['coordinator', 'worker', 'evaluator', 'reflector', 'reviewer'])
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    from native_check_plan import build, validate
    path = run_dir/'native-check-plan.json'
    plan = validate(json.loads(path.read_text()), ROOT) if path.is_file() else build(ROOT)
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
        result = execute([node['path'], '--test', *map(str, sorted((ROOT / 'tests').glob('*.test.js')))], ROOT, run_dir / 'javascript-tests.log',
                         normal=plan['worker']['normalSeconds'], maximum=plan['worker']['maximumSeconds'],
                         calibration=plan['calibration'])
        write(run_dir / 'worker-result.json', result)
        # Test failure is recorded evidence; the downstream reviewer must inspect it.
    elif args.role == 'evaluator':
        report = {'scope': plan['scope'], 'plannedModules': [r['module'] for r in plan['modules']],
                  'status': 'running', 'steps': []}
        result = {'exitCode': 0, 'command': [], 'output': 'native-check-report.json'}
        for row in plan['modules']:
            output = run_dir/('native-' + row['module'].removesuffix('.py') + '.log')
            report['activeModule'] = row['module']
            write(run_dir/'native-check-report.json', report)
            print('NATIVE_CHECK_STARTED ' + json.dumps(row), flush=True)
            observed = execute([sys.executable, str(ROOT/'scripts/run_test_module.py'), row['module']],
                               ROOT, output, normal=row['normalSeconds'], maximum=row['maximumSeconds'],
                               calibration=plan['calibration'])
            cases=[]
            for line in output.read_text(errors='replace').splitlines():
                if line.startswith('TEST_CASE_RESULT '):
                    try:
                        cases.append(json.loads(line.removeprefix('TEST_CASE_RESULT ')))
                    except ValueError:
                        pass  # Raw output is retained even if termination split a record.
            if observed['exitCode'] == 0 and (len(cases) != row['cases'] or any(c.get('status') != 'passed' for c in cases)):
                observed.update(exitCode=1, error='Native case evidence is incomplete or includes non-passing cases')
            report['steps'].append({**row, **observed, 'testCases': cases})
            write(run_dir/'native-check-report.json', report)
            if observed['exitCode']:
                result = observed
                break
        report['status'] = 'completed' if result['exitCode'] == 0 else 'failed'
        write(run_dir/'native-check-report.json', report)
        write(run_dir/'evaluator-result.json', result)
        if result['exitCode'] in (124, 130, 143):
            return result['exitCode']
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
    def stop(signum, frame):
        import check_steps
        check_steps.INTERRUPT_SIGNAL = signal.Signals(signum).name
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
