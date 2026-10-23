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
sys.path.insert(0, str(ROOT/'scripts'))
from runtime_service import WORKFLOW_TASKS  # noqa: E402
from matrix_scenarios import round_parameters  # noqa: E402
from challenge_bank import catalog_batch, catalog_v3  # noqa: E402

ROUNDS = 3
MIN_COVERAGE_PERCENT = 60
LOG_LIMIT = 4 * 1024 * 1024
ARCHIVE_LIMIT = 48 * 1024 * 1024
MODES = ('omitted', 'standard', 'explore')
PROFILES = ('smoke', 'full', 'bank')
REPETITIONS = ('default', 1, 2, 3)
CONFIG_IDS = {f'{canonical}-{profile}-{mode}-final{repeats}'
              for canonical in ('canonical', 'legacy') for profile in PROFILES
              for mode in MODES for repeats in REPETITIONS}
OTHER_IDS = ({f'llm-{profile}-timeout{timeout}' for profile in ('smoke', 'full')
              for timeout in ('default', 10, 3600)} |
             {f'skill-candidates{candidates}' for candidates in range(1, 5)} |
             {f'repair-seconds{seconds}-timeout{timeout}-calls{budget}'
              for seconds in (60, 7200) for timeout in (10, 3600) for budget in (2, 12)})
CASE_PATTERN = re.compile(r'test_gepa_configuration_freezes_complete_major_option_matrix\[([^]]+)\]\s+PASSED')
OTHER_PATTERN = re.compile(r'test_other_workflow_option_matrix_(?:llm|skill|repair)\[([^]]+)\]\s+PASSED')
REPORT_PATTERN = re.compile(r'^Support report: (.+/report\.json)$', re.MULTILINE)
V3_METHODS = ('test_v3_frozen_dataset_all_three_verifiers_frontend_and_approval',
              'test_v3_second_distinct_batch_in_matrix_round')
V3_STEP_PREFIX = 'python-challenge_v3_workflow_test--challenge_v3_workflow_test.ChallengeV3WorkflowTests.'
WORKFLOW_MODULES = {
    'project-health': ('python-runtime_test',),
    'skill-evolution': ('python-skill_test',),
    'llm-evolution': ('python-llm_test',),
    'nanobot-repair': ('python-repair_test',),
    'gepa-evolution': ('python-gepa_test',),
}
VARIANT_MODULES = {
    'ollama-strata': ('python-provider_switch_test', 'python-strata_workflow_test'),
    'challenge-v2': ('python-challenge_v2_workflow_test',),
    'challenge-v3': ('python-challenge_v3_workflow_test', 'python-challenge_v3_test'),
}
FLOW_PATHS = {
    'project-health': ('python-runtime_test', None),
    'skill-evolution': ('python-skill_test', None),
    'llm-evolution:ollama': ('python-llm_test', None),
    'llm-evolution:strata': ('python-strata_workflow_test', 'test_llm_reflection_review_approval_and_rollback'),
    'nanobot-repair:ollama': ('python-repair_test', None),
    'nanobot-repair:strata': ('python-strata_workflow_test', 'test_real_nanobot_streamed_tools_and_independent_reviewer'),
    'gepa-evolution:ollama': ('python-gepa_test', None),
    'gepa-evolution:strata': ('python-strata_workflow_test', 'test_real_gepa_search_final_review_approval_rollback_and_tamper_gate'),
}
if set(WORKFLOW_MODULES) != set(WORKFLOW_TASKS):
    raise RuntimeError('Matrix catalog does not cover every RuntimeService workflow')
if {name.split(':')[0] for name in FLOW_PATHS} != set(WORKFLOW_TASKS):
    raise RuntimeError('Runtime/provider path catalog omits a supported workflow')


def release_step_names(root):
    from scripts.check_start_selection import release_plan
    from scripts.gepa_validation_budget import expand_plan
    return [name for name, _ in expand_plan(release_plan(root, 'python', 'node'), root)]


def covered_workflows(steps):
    """A workflow is covered only by executed, nonempty release test modules."""
    modules = {row['step'] for row in steps if row.get('status') == 'completed'
               and row.get('testCases') and all(case.get('status') == 'passed'
                                                for case in row['testCases'])}
    required = {**WORKFLOW_MODULES, **VARIANT_MODULES}
    return {name: all(any(step == prefix or step.startswith(prefix+'--') for step in modules)
                      for prefix in prefixes) for name, prefixes in required.items()}


def covered_flow_paths(steps):
    """Only passed cases from the release report count as runtime/provider paths."""
    passed = [(row['step'], [case['test'] for case in row.get('testCases', [])
                            if case.get('status') == 'passed']) for row in steps
              if row.get('status') == 'completed']
    return {name: any((step == prefix or step.startswith(prefix+'--')) and
                      (any(case.endswith('.'+method) for case in cases) if method else bool(cases))
                      for step, cases in passed) for name, (prefix, method) in FLOW_PATHS.items()}


def read_round_variant(root, child, steps, round_number):
    """Validate recorded real-SDK V3 question IDs and parameters, not just a round label."""
    expected = round_parameters(round_number)
    matching = [row for row in steps if row['step'].startswith(V3_STEP_PREFIX)]
    if {row['step'] for row in matching} != {V3_STEP_PREFIX+name for name in V3_METHODS}:
        raise ValueError('Both independently supervised V3 workflow steps are required')
    rows = []
    for step in matching:
        cases = step.get('testCases', [])
        if (len(cases) != 1 or cases[0].get('test') != step['step'].removeprefix('python-challenge_v3_workflow_test--')
                or cases[0].get('status') != 'passed' or step.get('log') != step['step']+'.log'):
            raise ValueError('V3 workflow case or log does not match its supervised step')
        path = child.parent/step['log']
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('V3 workflow evidence is missing or exceeds the evidence bound')
        rows.extend(json.loads(line.removeprefix('M_MATRIX_V3 ')) for line in path.read_text().splitlines()
                    if line.startswith('M_MATRIX_V3 '))
    if len(rows) != 2 or {row.get('batch') for row in rows} != set(expected['batches']):
        raise ValueError('This round did not run its two distinct V3 batches')
    catalog = catalog_v3()
    for row in rows:
        if (row.get('round') != round_number or row.get('taskCallBudget') != expected['taskCallBudget']
                or row.get('maxSeconds') != expected['maxSeconds']
                or row.get('taskIds') != sorted(catalog_batch(catalog, row['batch']))
                or not isinstance(row.get('datasetHash'), str)
                or re.fullmatch(r'[a-f0-9]{64}', row['datasetHash']) is None):
            raise ValueError('V3 batch questions, parameters or frozen dataset evidence differ from the plan')
    return sorted(rows, key=lambda row: row['batch'])


def coverage_report(attempts, release_steps, catalog):
    """Coverage of the finite, source-owned workflow paths; arbitrary numeric inputs are excluded."""
    successful = [row for row in attempts if row['status'] == 'passed']
    config = set().union(*(row.get('configurationsPassed', []) for row in successful))
    other = set().union(*(row.get('otherOptionsPassed', []) for row in successful))
    paths = {name for row in successful for name, passed in row.get('flowPathsPassed', {}).items() if passed}
    batches = {row['batch'] for attempt in successful for row in attempt.get('v3Variants', [])}
    questions = {identifier for attempt in successful for row in attempt.get('v3Variants', [])
                 for identifier in row['taskIds']}
    required = ({'gepa:'+name for name in CONFIG_IDS} |
                {'other:'+name for name in OTHER_IDS} |
                {'workflow:'+name for name in FLOW_PATHS} |
                {'v3-batch:'+str(index) for index in range(5)})
    covered = ({'gepa:'+name for name in config} | {'other:'+name for name in other} |
               {'workflow:'+name for name in paths} | {'v3-batch:'+str(index) for index in batches}) & required
    catalog_ids = {row['id'] for row in catalog}
    return {'minimumRatePercent': MIN_COVERAGE_PERCENT,
            'ratePercent': round(100*len(covered)/len(required), 2),
            'coveredPaths': len(covered), 'totalPaths': len(required),
            'missingPaths': sorted(required-covered),
            'modelQuestionRatePercent': round(100*len(questions & catalog_ids)/len(catalog_ids), 2),
            'modelQuestionsCovered': len(questions & catalog_ids), 'modelQuestionsTotal': len(catalog_ids),
            'missingModelQuestions': sorted(catalog_ids-questions),
            'distinctV3Batches': sorted(batches),
            'releaseStepsExpectedPerRound': len(release_steps)}


def matrix_plan(root):
    python = str(root/'.venv-m/bin/python')
    return [
        ('configurations', [python, '-m', 'pytest', '-s', '-vv', 'tests_m/test_phase_m_config_matrix.py']),
        ('other-options', [python, '-m', 'pytest', '-s', '-vv', 'tests_m/test_phase_m_other_options.py']),
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
    environment = {**os.environ, **({'M_MATRIX_ROUND': str(round_number)} if round_number else {})}
    process = subprocess.Popen(command, cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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


def read_acceptance(root, output, source_hash, round_number):
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
    expected_steps = release_step_names(root)
    if (nested.get('profile') != 'release' or nested.get('status') != 'completed'
            or nested.get('scope') or [row.get('step') for row in steps] != expected_steps
            or any(row.get('status') != 'completed' or any(
                case.get('status') != 'passed' for case in row.get('testCases', [])) for row in steps)):
        raise ValueError('Nested release was incomplete, scoped or contained a skipped case')
    workflow_evidence = covered_workflows(steps)
    if not all(workflow_evidence.values()):
        raise ValueError('A declared workflow/provider/bank has no passing release test module: '
                         + ', '.join(name for name, passed in workflow_evidence.items() if not passed))
    path_evidence = covered_flow_paths(steps)
    if not all(path_evidence.values()):
        raise ValueError('A supported workflow/provider path has no passed release case: '
                         + ', '.join(name for name, passed in path_evidence.items() if not passed))
    variants = read_round_variant(root, child, steps, round_number)
    return (path, stages, child, expected_steps, sum(len(row.get('testCases', [])) for row in steps),
            workflow_evidence, path_evidence, variants)


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
            for case_index, method in enumerate(V3_METHODS, 1):
                variant_log = path.parent/(V3_STEP_PREFIX+method+'.log')
                label = f'v3-workflow-round{index}-case{case_index}'
                if variant_log.is_file() and not variant_log.is_symlink() and variant_log.stat().st_size <= LOG_LIMIT:
                    variant = redact(variant_log.read_text(errors='replace')).encode()
                    if total + len(variant) <= ARCHIVE_LIMIT:
                        variant_name = f'acceptance/round{index}/v3-workflow-case{case_index}.log'
                        archive.writestr(variant_name, variant)
                        total += len(variant)
                        included.append({'name': variant_name, 'bytes': len(variant),
                                         'sha256': hashlib.sha256(variant).hexdigest()})
                    else:
                        omitted.append({'name': label, 'reason': 'size-limit'})
                else:
                    omitted.append({'name': label, 'reason': 'missing-or-size-limit'})
        archive.writestr('archive-manifest.json', canonical({'included': included, 'omitted': omitted,
                                                              'totalInputBytes': total}))
    return target


def run_matrix(root=ROOT, *, plan=None, source_hash=None, output=None, prepare_docker=False):
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
               'roundScenarios': [round_parameters(number) for number in range(1, ROUNDS+1)],
               'configurationsRequired': sorted(CONFIG_IDS), 'otherOptionsRequired': sorted(OTHER_IDS),
               'fullPlan': [name for name, _ in plan] == [name for name, _ in matrix_plan(root)],
               'plan': [{'flow': name, 'command': command, 'rounds': ROUNDS} for name, command in plan],
               'dockerPreparationRequested': prepare_docker,
               'attempts': [], 'status': 'running', 'limits': ['Scripted loopback provider; no real Windows GPU qualification']}
    atomic_write(output/'summary.json', canonical(summary))
    append_event(events, 'matrix.started', sourceCommit=head, sourceHash=source_hash)
    reports, nested_reports = [], []
    failed = False
    try:
        if prepare_docker:
            prep = output/'prepare-docker.log'
            command = ['timeout', '1800', 'bash', 'scripts/build-m-images.sh']
            code, _ = run_command(root, command, prep, events, 'prepare-docker', 0)
            summary['dockerPreparation'] = {'command': command, 'exitCode': code,
                                            'status': 'passed' if code == 0 else 'failed', 'log': prep.name}
            atomic_write(output/'summary.json', canonical(summary))
            if code:
                failed = True
        for flow, command in plan:
            if failed:
                break
            for round_number in range(1, ROUNDS+1):
                if source_snapshot(root)[0] != source_hash or subprocess.run(
                    ['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True
                ).stdout.strip() != head:
                    raise RuntimeError('Source changed during the frozen matrix')
                log = output/f'{flow}-round{round_number}.log'
                attempt = {'flow': flow, 'round': round_number, 'startedAt': timestamp(),
                           'command': command, 'scenario': round_parameters(round_number),
                           'sourceHash': source_hash, 'log': log.name}
                try:
                    code, text = run_command(root, command, log, events, flow, round_number)
                    attempt['exitCode'] = code
                    if code:
                        raise RuntimeError(f'{flow} round {round_number} exited {code}')
                    if flow == 'configurations':
                        covered = set(CASE_PATTERN.findall(text))
                        if covered != CONFIG_IDS or '73 passed' not in text or 'skipped' in text:
                            raise ValueError('Configuration matrix is missing a passing combination')
                        attempt['configurationsPassed'] = sorted(covered)
                    elif flow == 'other-options':
                        covered = set(OTHER_PATTERN.findall(text))
                        if covered != OTHER_IDS or '18 passed' not in text or 'skipped' in text:
                            raise ValueError('Other workflow option matrix is missing a passing combination')
                        attempt['otherOptionsPassed'] = sorted(covered)
                    elif flow == 'acceptance':
                        (report, attempt['stages'], nested, steps, cases, workflows, paths, variants) = read_acceptance(
                            root, text, source_hash, round_number)
                        attempt['supportReport'] = str(report.relative_to(root))
                        attempt['nestedReport'] = str(nested.relative_to(root))
                        attempt['releaseSteps'] = len(steps)
                        attempt['releaseStepIds'] = steps
                        attempt['releaseCases'] = cases
                        attempt['workflowsPassed'] = workflows
                        attempt['flowPathsPassed'] = paths
                        attempt['v3Variants'] = variants
                        reports.append(report)
                        nested_reports.append(nested)
                    elif flow == 'components':
                        # The component-only M4 Docker case is intentionally skipped;
                        # real isolation is required and checked by acceptance.
                        summaries = re.findall(
                            r'(?m)^\s*(\d+) passed(?:, (\d+) skipped)?(?:, \d+ warnings)? in [\d.]+s\s*$', text)
                        attempt['componentDockerSkip'] = int(summaries[-1][1] or 0) if summaries else None
                        # check_m streams pytest and then prints its captured output;
                        # both copies include the same terminal summary.
                        if not summaries or attempt['componentDockerSkip'] > 1:
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
                               'workflowPasses': {name: sum(a.get('workflowsPassed', {}).get(name, False)
                                                              and a['status'] == 'passed' for a in summary['attempts'])
                                                  for name in (*WORKFLOW_MODULES, *VARIANT_MODULES)},
                               'releaseStepPasses': {step: sum(step in a.get('releaseStepIds', []) and a['status']=='passed'
                                                              for a in summary['attempts'])
                                                     for step in release_step_names(root)} if not failed or
                                                     any(a['flow']=='acceptance' for a in summary['attempts']) else {},
                               'unexecuted': [{'flow': flow, 'round': number}
                                              for flow, _ in plan for number in range(1, ROUNDS+1)
                                              if not any(a['flow']==flow and a['round']==number for a in summary['attempts'])]}
        summary['coverage'].update(coverage_report(summary['attempts'], release_step_names(root), catalog_v3()))
        complete = not failed and all(value == ROUNDS for value in counts.values())
        if summary['fullPlan']:
            complete = (complete and summary['coverage']['ratePercent'] >= MIN_COVERAGE_PERCENT
                        and summary['coverage']['modelQuestionRatePercent'] == 100
                        and summary['coverage']['distinctV3Batches'] == list(range(5)))
        summary['status'] = ('passed' if summary['fullPlan'] else 'scoped_passed') if complete else 'incomplete'
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
    parser.add_argument('--list-plan', action='store_true', help='Show 72 option paths and three runs per flow without dispatch')
    parser.add_argument('--prepare-docker', action='store_true', help='Build the pinned Docker evaluator image before the matrix')
    args = parser.parse_args()
    if args.list_plan:
        print(json.dumps({'combinations': sorted(CONFIG_IDS), 'otherOptions': sorted(OTHER_IDS),
                          'roundScenarios': [round_parameters(number) for number in range(1, ROUNDS+1)],
                          'minimumCoveragePercent': MIN_COVERAGE_PERCENT, 'rounds': ROUNDS,
                          'plan': matrix_plan(ROOT)}, ensure_ascii=False, indent=2))
    else:
        raise SystemExit(run_matrix(output=args.output, prepare_docker=args.prepare_docker))
