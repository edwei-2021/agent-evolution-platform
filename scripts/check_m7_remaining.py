#!/usr/bin/env python3
"""Run the failed release case and M7 tail, with explicit historical evidence scope."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import check_steps
from platform_m.gates import source_snapshot
from platform_m.evidence import canonical, redact, archive_failure_evidence


def prior_failure(path):
    raw = Path(path).read_bytes()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as bundle:
            report_name = 'release/report.json' if 'release/report.json' in bundle.namelist() else 'report.json'
            info = bundle.getinfo(report_name)
            if info.file_size > 10_000_000:
                raise ValueError('Prior release report is too large')
            report = json.loads(bundle.read(info))
    else:
        report = json.loads(raw)
    if report.get('profile') != 'release' or report.get('status') != 'failed':
        raise ValueError('Expected a failed release report or its M support ZIP')
    rows = report.get('steps', [])
    failed = next((row for row in rows if row.get('status') != 'completed'), None)
    scoped = report.get('scope', {}).get('kind') == 'm7-remaining'
    if not failed or failed.get('status') != 'failed':
        raise ValueError('Resume requires a failed step')
    if not scoped and not failed.get('step', '').startswith('python-'):
        raise ValueError('An initial resume requires a failed release Python module')
    if any(row.get('status') != 'completed' for row in rows[:rows.index(failed)]):
        raise ValueError('Earlier release evidence is incomplete')
    cases = failed.get('testCases', [])
    anchor = next((row for row in cases if row.get('status') in ('failed', 'error')), None)
    if (not anchor and not scoped) or (anchor and any(
            row.get('status') != 'passed' for row in cases[:cases.index(anchor)])):
        raise ValueError('Cannot identify an unambiguous first failed case')
    return report, failed['step'], anchor['test'] if anchor else None, hashlib.sha256(raw).hexdigest()


def remaining_plan(plan, failed_step, anchor):
    failed_step = failed_step.split(':', 1)[0].split('--', 1)[0]
    names = [name for name, _ in plan]
    if failed_step not in names:
        raise ValueError('Prior failed module no longer exists in the release plan')
    index = names.index(failed_step)
    module = failed_step.removeprefix('python-')
    if not anchor.startswith(module + '.'):
        raise ValueError('Failed case does not belong to the failed module')
    selected = [(name, list(command)) for name, command in plan[index:]]
    selected[0][1].extend(['--from-case', anchor])
    return selected, names[:index]


def build_plan(release_plan, prior, failed_step, anchor, node):
    scoped = prior.get('scope', {}).get('kind') == 'm7-remaining'
    origin = (prior['scope'].get('releaseFromCase') or prior['scope'].get('fromCase')) if scoped else anchor
    if not isinstance(origin, str) or '.' not in origin:
        raise ValueError('Missing original release case provenance')
    origin_step = 'python-' + origin.split('.', 1)[0]
    plan, omitted = remaining_plan(release_plan, origin_step, origin)
    python = plan[0][1][0]
    m_python = str(ROOT/'.venv-m/bin/python')
    legacy = scoped and (failed_step in {'native-regressions', 'monitor-regressions',
                                        'frontend-regressions', 'm7-unit', 'resume-regressions'} or
                         prior['scope'].get('legacyHarnessTail', False))
    if legacy:
        plan.extend([
            ('native-regressions', [python, str(ROOT/'scripts/run_test_module.py'), 'native_checks_test.py']),
            ('monitor-regressions', [python, str(ROOT/'scripts/run_test_module.py'), 'check_steps_test.py']),
            ('frontend-regressions', [node, '--test', *map(str, sorted((ROOT/'tests').glob('*.test.js')))]),
            ('m7-unit', [m_python, '-m', 'pytest', '-s', '-vv', '--durations=0', 'tests_m/test_m7.py', 'tests_m/test_gates.py']),
        ])
    plan.extend([
        ('m7-source-scan', [m_python, str(ROOT/'scripts/scan_m_source.py')]),
        ('m7-ruff', [m_python, '-m', 'ruff', 'check', 'platform_m', 'tests_m',
                     'scripts/generate_m_contracts.py', 'scripts/migrate_wsl.py',
                     'scripts/check_m.py', 'scripts/check_m_environment.py', 'scripts/serve_m.py',
                     'scripts/check_steps.py', 'scripts/run_test_module.py',
                     'scripts/calibrate_release_tests.py', 'scripts/check_m7_remaining.py',
                     'scripts/native_agents.py', 'scripts/native_check_plan.py', 'scripts/native_check_support.py',
                     'scripts/gepa_validation_budget.py', 'scripts/check_start_selection.py']),
        ('m7-types', [node, 'node_modules/typescript/bin/tsc', '--noEmit', '--strict',
                      '--lib', 'es2020,dom', 'packages/contracts/contracts.ts']),
    ])
    from gepa_validation_budget import expand_plan
    plan = expand_plan(plan, ROOT)
    completed = []
    if scoped:
        if failed_step.startswith('python-gepa_test:'):
            failed_step = failed_step.replace('python-gepa_test:', 'python-gepa_test--', 1)
        names = [name for name, _ in plan]
        if failed_step == 'filesystem-calibration':
            pass  # It is always repeated before the remaining checks.
        elif failed_step not in names:
            raise ValueError('Prior failed step no longer exists in the safe continuation plan')
        else:
            index = names.index(failed_step)
            completed = names[:index]
            plan = plan[index:]
            command = plan[0][1]
            for option in ('--case', '--from-case'):
                if option in command:
                    del command[command.index(option):]
            if anchor:
                if not any(Path(arg).name == 'run_test_module.py' for arg in command):
                    raise ValueError('Case selection requires the known unittest runner')
                pattern = command[2]
                if not anchor.startswith(pattern.removesuffix('.py') + '.'):
                    raise ValueError('Failed case does not belong to the selected runner module')
                command.extend(['--case' if failed_step.startswith(('python-gepa_test--', 'python-gepa_test:')) else '--from-case', anchor])
    # Filesystem calibration is cheap, and must precede frozen workflow budgets.
    plan.insert(0, ('filesystem-calibration', [python, str(ROOT/'scripts/calibrate_release_tests.py')]))
    return plan, omitted, completed, origin


def archive_report(directory):
    archive = directory/'support.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(directory.iterdir()):
            if path.suffix == '.json':
                bundle.writestr(path.name, canonical(redact(json.loads(path.read_text()))))
            elif path.suffix == '.log':
                bundle.writestr(path.name, redact(path.read_text(errors='replace')))
        archive_failure_evidence(bundle, directory)
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--previous-support', type=Path,
                        help='Failed M support ZIP, continuation ZIP, or release/report.json')
    source.add_argument('--from-case', help='Explicit failed case from terminal evidence; no prior archive verification claimed')
    args = parser.parse_args(argv)
    try:
        if args.previous_support:
            prior, failed_step, anchor, prior_sha = prior_failure(args.previous_support)
        else:
            anchor = args.from_case
            if not isinstance(anchor, str) or anchor.count('.') != 2:
                raise ValueError('Expected a fully qualified failed case ID')
            prior = {'evidenceKind': 'user-supplied terminal case anchor; archive not available'}
            failed_step, prior_sha = 'python-' + anchor.split('.')[0], None
        m_python = ROOT/'.venv-m/bin/python'
        if not m_python.is_file():
            raise ValueError('M environment missing; run bash scripts/install-m.sh before continuation')
        preflight = subprocess.run([str(m_python), '-c', "import importlib.metadata as m; [m.version(n) for n in ('fastapi','httpx','pytest','ruff')]"],
                                   cwd=ROOT, capture_output=True, text=True, timeout=30)
        if preflight.returncode:
            raise ValueError('M test dependencies unavailable; run bash scripts/install-m.sh: ' + preflight.stderr[-2000:])
        if not (ROOT/'node_modules/typescript/bin/tsc').is_file():
            raise ValueError('TypeScript dependency missing; run npm ci before continuation')
        node = check_steps.find_node(ROOT)
        if not node:
            raise ValueError('Supported Node runtime is required')
        plan, omitted, completed, origin = build_plan(
            check_steps.stages('release'), prior, failed_step, anchor, node['path'])
        source_hash, inputs = source_snapshot(ROOT)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    scope = {'kind': 'm7-remaining', 'fullMAcceptance': False, 'fullM7Acceptance': False,
             'priorEvidenceKind': prior.get('evidenceKind', 'support artifact'),
             'legacyHarnessTail': any(name == 'monitor-regressions' for name, _ in plan),
             'priorReportId': prior.get('id'), 'priorArtifactSha256': prior_sha,
             'priorEvidence': 'historical only; not re-certified against this source',
             'fromCase': origin, 'releaseFromCase': origin, 'resumedFromStep': failed_step,
             'failedCase': anchor, 'omittedReleaseSteps': omitted, 'completedPriorTailSteps': completed,
             'sourceHash': source_hash, 'inputHashes': inputs,
             'plannedSteps': [name for name, _ in plan]}
    print('M7_SCOPE ' + json.dumps({k: v for k, v in scope.items() if k != 'inputHashes'}), flush=True)
    identifier = 'CHECK-' + uuid.uuid4().hex
    result = check_steps.run('release', interactive=False, plan=plan, metadata=scope, identifier=identifier)
    archive = archive_report(ROOT/'.local/test-reports'/identifier)
    print('M7_REMAINING_SUPPORT ' + str(archive), flush=True)
    return result


if __name__ == '__main__':
    def terminate(signum, frame):
        check_steps.INTERRUPT_SIGNAL = signal.Signals(signum).name
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
