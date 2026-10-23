#!/usr/bin/env python3
"""Unattended three-round M acceptance matrix with bounded, downloadable evidence."""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from platform_m.evidence import atomic_write, canonical, redact  # noqa: E402
from platform_m.gates import source_snapshot  # noqa: E402

ROUNDS = 3
LOG_LIMIT = 4 * 1024 * 1024
ARCHIVE_LIMIT = 48 * 1024 * 1024
MODES = ('omitted', 'standard', 'explore')
PROFILES = ('smoke', 'full', 'bank')
REPETITIONS = (1, 3)
CONFIG_IDS = {f'{profile}-{mode}-final{repeats}' for profile in PROFILES
              for mode in MODES for repeats in REPETITIONS}
CASE_PATTERN = re.compile(r'test_gepa_configuration_freezes_complete_major_option_matrix\[([^]]+)\]\s+PASSED')
REPORT_PATTERN = re.compile(r'^Support report: (.+/report\.json)$', re.MULTILINE)


def matrix_plan(root):
    python = str(root/'.venv-m/bin/python')
    return [
        ('configurations', [python, '-m', 'pytest', '-s', '-vv', 'tests_m/test_phase_m_config_matrix.py']),
        ('components', [python, 'scripts/check_m.py', '--profile', 'components', '--non-interactive']),
        ('acceptance', [python, 'scripts/check_m.py', '--profile', 'acceptance', '--non-interactive']),
    ]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def append_event(path, kind, **facts):
    with path.open('ab') as stream:
        stream.write(canonical({'at': timestamp(), 'kind': kind, **facts}) + b'\n')
        stream.flush()


def run_command(root, command, log_path, events, flow, round_number):
    process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors='replace', bufsize=1, start_new_session=True,
                               stdin=subprocess.DEVNULL)
    tail, tail_bytes = deque(), 0
    started = time.monotonic()
    append_event(events, 'process.started', flow=flow, round=round_number, pid=process.pid)
    try:
        for line in process.stdout:
            safe = redact(line)
            print(safe, end='', flush=True)
            encoded = safe.encode()
            tail.append(encoded)
            tail_bytes += len(encoded)
            while tail_bytes > LOG_LIMIT and len(tail) > 1:
                tail_bytes -= len(tail.popleft())
        code = process.wait()
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    finally:
        prefix = b'[Earlier output omitted; see stage reports for bounded command details.]\n' if tail_bytes >= LOG_LIMIT else b''
        atomic_write(log_path, prefix + b''.join(tail)[-LOG_LIMIT:])
    append_event(events, 'process.finished', flow=flow, round=round_number,
                 exitCode=code, elapsedSeconds=round(time.monotonic()-started, 3), logBytes=log_path.stat().st_size)
    return code, log_path.read_text(errors='replace')


def read_acceptance(root, output, source_hash):
    expected = (root/'.local/m/support').resolve()
    matches = [path for value in REPORT_PATTERN.findall(output)
               if (path := Path(value).resolve()).name == 'report.json'
               and path.parent.parent == expected]
    if len(matches) != 1:
        raise ValueError('Exactly one current-checkout M support report is required')
    path = matches[0]
    report = json.loads(path.read_text())
    stages = {row['step']: row['status'] for row in report['checks']}
    if (report['source_hash'] != source_hash or report['status'] != 'passed'
            or report.get('scope', {}).get('fullMAcceptance') is not True
            or stages != {f'M{i}': 'passed' for i in range(1, 8)}):
        raise ValueError('M1–M7 did not all pass on the frozen source')
    m7 = json.loads((path.parent/'M7.json').read_text())
    children = [row['child_report'] for row in m7['logs'] if row.get('child_report')]
    if len(children) != 1:
        raise ValueError('Exactly one nested full release report is required')
    child = Path(children[0]).resolve()
    if child.name != 'report.json' or not child.is_relative_to((root/'.local/test-reports').resolve()):
        raise ValueError('Nested release evidence escaped the test directory')
    nested = json.loads(child.read_text())
    steps = nested.get('steps', [])
    if (nested.get('profile') != 'release' or nested.get('status') != 'passed'
            or nested.get('scope') or not steps
            or any(row.get('status') != 'completed' or any(
                case.get('status') != 'passed' for case in row.get('testCases', [])) for row in steps)):
        raise ValueError('Nested release was incomplete, scoped or contained a skipped case')
    return path, stages, child, len(steps), sum(len(row.get('testCases', [])) for row in steps)


def archive_evidence(directory, report_paths, nested_paths):
    target = directory/'support.zip'
    included, omitted, total = [], [], 0
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        files = [directory/'summary.json', directory/'events.jsonl', *sorted(directory.glob('*.log'))]
        for index, path in enumerate(report_paths, 1):
            files.extend(sorted(path.parent.glob('M[1-7].json')))
            files.append(path)
        for path in files:
            if not path.is_file() or path.is_symlink():
                omitted.append({'name': path.name, 'reason': 'missing-or-symlink'})
                continue
            size = path.stat().st_size
            if size > LOG_LIMIT or total + size > ARCHIVE_LIMIT:
                omitted.append({'name': path.name, 'reason': 'size-limit', 'bytes': size})
                continue
            name = (f'acceptance/{path.parent.name}/{path.name}' if path in report_paths or
                    path.parent in {p.parent for p in report_paths} else path.name)
            archive.write(path, name)
            total += size
            included.append({'name': name, 'bytes': size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for index, path in enumerate(nested_paths, 1):
            if not path.is_file() or path.is_symlink():
                omitted.append({'name': f'nested-{index}', 'reason': 'missing-or-symlink'})
                continue
            raw = canonical(redact(json.loads(path.read_text())))
            if len(raw) > LOG_LIMIT or total + len(raw) > ARCHIVE_LIMIT:
                omitted.append({'name': f'nested-{index}', 'reason': 'size-limit', 'bytes': len(raw)})
                continue
            name = f'acceptance/round{index}/release-report.json'
            archive.writestr(name, raw)
            total += len(raw)
            included.append({'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        archive.writestr('archive-manifest.json', canonical({'included': included, 'omitted': omitted,
                                                              'totalInputBytes': total}))
    return target


def run_matrix(root=ROOT, *, plan=None, source_hash=None, output=None):
    root = Path(root).resolve()
    output = Path(output or root/'.local/m/matrix'/('MATRIX-'+uuid.uuid4().hex)).resolve()
    output.mkdir(parents=True, exist_ok=False)
    events = output/'events.jsonl'
    plan = plan or matrix_plan(root)
    source_hash = source_hash or source_snapshot(root)[0]
    head = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                          capture_output=True, text=True, check=True).stdout.strip()
    summary = {'schema': 'phase-m-matrix-v1', 'sourceCommit': head, 'sourceHash': source_hash,
               'startedAt': timestamp(), 'roundsRequired': ROUNDS,
               'configurationsRequired': sorted(CONFIG_IDS),
               'fullPlan': [name for name, _ in plan] == [name for name, _ in matrix_plan(root)],
               'plan': [{'flow': name, 'command': command, 'rounds': ROUNDS} for name, command in plan],
               'attempts': [], 'status': 'running', 'limits': ['Scripted loopback provider; no real Windows GPU qualification']}
    atomic_write(output/'summary.json', canonical(summary))
    append_event(events, 'matrix.started', sourceCommit=head, sourceHash=source_hash)
    reports, nested_reports = [], []
    failed = False
    try:
        for flow, command in plan:
            for round_number in range(1, ROUNDS+1):
                if source_snapshot(root)[0] != source_hash or subprocess.run(
                    ['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True
                ).stdout.strip() != head:
                    raise RuntimeError('Source changed during the frozen matrix')
                log = output/f'{flow}-round{round_number}.log'
                attempt = {'flow': flow, 'round': round_number, 'startedAt': timestamp(),
                           'command': command, 'sourceHash': source_hash, 'log': log.name}
                try:
                    code, text = run_command(root, command, log, events, flow, round_number)
                    attempt['exitCode'] = code
                    if code:
                        raise RuntimeError(f'{flow} round {round_number} exited {code}')
                    if flow == 'configurations':
                        covered = set(CASE_PATTERN.findall(text))
                        if covered != CONFIG_IDS or '19 passed' not in text or 'skipped' in text:
                            raise ValueError('Configuration matrix is missing a passing combination')
                        attempt['configurationsPassed'] = sorted(covered)
                    elif flow == 'acceptance':
                        report, attempt['stages'], nested, steps, cases = read_acceptance(root, text, source_hash)
                        attempt['supportReport'] = str(report.relative_to(root))
                        attempt['nestedReport'] = str(nested.relative_to(root))
                        attempt['releaseSteps'] = steps
                        attempt['releaseCases'] = cases
                        reports.append(report)
                        nested_reports.append(nested)
                    elif flow == 'components':
                        # The component-only M4 Docker case is intentionally skipped;
                        # real isolation is required and checked by acceptance.
                        skipped = re.search(r'\b(\d+) skipped\b', text)
                        attempt['componentDockerSkip'] = int(skipped[1]) if skipped else 0
                        if (not re.search(r'\b\d+ passed\b', text) or ' failed' in text
                                or attempt['componentDockerSkip'] > 1):
                            raise ValueError('Component pytest summary is incomplete')
                    attempt['status'] = 'passed'
                except Exception as exc:
                    attempt.update(status='failed', errorType=type(exc).__name__, error=str(exc))
                    failed = True
                finally:
                    attempt['finishedAt'] = timestamp()
                    summary['attempts'].append(attempt)
                    atomic_write(output/'summary.json', canonical(summary))
                    append_event(events, 'attempt.finished', flow=flow, round=round_number,
                                 status=attempt['status'], exitCode=attempt.get('exitCode'))
                if failed:
                    break
            if failed:
                break
    except BaseException as exc:
        summary['interruption'] = {'type': type(exc).__name__, 'at': timestamp()}
        failed = True
    finally:
        summary['finishedAt'] = timestamp()
        counts = {flow: sum(a['status']=='passed' for a in summary['attempts'] if a['flow']==flow)
                  for flow, _ in plan}
        summary['coverage'] = {'flowPasses': counts, 'expectedPerFlow': ROUNDS,
                               'unexecuted': [{'flow': flow, 'round': number}
                                              for flow, _ in plan for number in range(1, ROUNDS+1)
                                              if not any(a['flow']==flow and a['round']==number for a in summary['attempts'])]}
        summary['status'] = ('passed' if summary['fullPlan'] else 'scoped_passed') if not failed and all(
            value == ROUNDS for value in counts.values()) else 'incomplete'
        atomic_write(output/'summary.json', canonical(summary))
        append_event(events, 'matrix.finished', status=summary['status'], flowPasses=counts)
        archive = archive_evidence(output, reports, nested_reports)
        print('M_MATRIX_SUMMARY ' + str(output/'summary.json'), flush=True)
        print('M_MATRIX_ARCHIVE ' + str(archive), flush=True)
    return 0 if summary['status'] in ('passed', 'scoped_passed') else 1


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError(f'Matrix received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New evidence directory; must not exist')
    parser.add_argument('--list-plan', action='store_true', help='Show 18 options and three runs per flow without dispatch')
    args = parser.parse_args()
    if args.list_plan:
        print(json.dumps({'combinations': sorted(CONFIG_IDS), 'rounds': ROUNDS,
                          'plan': matrix_plan(ROOT)}, ensure_ascii=False, indent=2))
    else:
        raise SystemExit(run_matrix(output=args.output))
