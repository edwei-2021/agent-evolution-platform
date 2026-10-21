"""Frozen loopback-fixture budgets; include all trusted replays, never production defaults."""
import ast
import math
from pathlib import Path


FULL_CASES = ('test_actual_js_client_to_python_api_dispatch_and_result_validation',
              'test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate',
              'test_perfect_seed_skips_proposals_and_cannot_release_without_improvement',
              'test_heldout_regression_blocks_release_even_with_validation_improvement')
APPROVAL_CASE = FULL_CASES[1]
MAX_SECONDS = 7200


def canonical_fixture_budget(io_seconds):
    """Two canonical cases: actual search/replay/approval and paused cancellation."""
    if not math.isfinite(io_seconds) or io_seconds<0:raise ValueError('Invalid canonical storage calibration')
    rollouts=10+2*(3+3);calls=rollouts*6+1
    workflow=120+calls*10+rollouts*(24*5+3*5)+30+8*15
    phases={'sdkAdmission':2*240,'sourceAdmission':2*15,'positiveWorkflow':workflow,
            'approvalReplay':math.ceil(rollouts*(5+2*io_seconds)),
            'cancelChildStartup':10,'pausedFinalizers':25,'terminalCollection':60,
            'setupAndTeardown':60+math.ceil(60*io_seconds)}
    maximum=sum(phases.values())
    if maximum>MAX_SECONDS:raise ValueError('Canonical fixture workload exceeds 7200s; inspect storage calibration')
    return {'policy':'canonical-gepa-fixture-v1','maximumRollouts':rollouts,'modelRequests':calls,
            'verificationBatches':3*rollouts,'approvalBatches':rollouts,'workflowSeconds':workflow,
            'normalSeconds':math.ceil(240+rollouts*(4+12*io_seconds)+phases['approvalReplay']),
            'maximumSeconds':maximum,'phasesSeconds':phases}


def smoke_budget(io_seconds):
    from gepa_dataset import dataset
    if not math.isfinite(io_seconds) or io_seconds < 0:
        raise ValueError('Invalid GEPA storage calibration')
    rows = dataset('smoke')
    total = 8 + 2 * (len(rows['validation']) + len(rows['heldout']))
    calls = total * 6 + 2  # task cap plus reflection cap; request deadline stays 10s
    # EACH rollout: one visible tool process, immediate verification, evaluator
    # replay, independent reviewer replay. Every trusted process is limited to 5s.
    phases = {
        'startup': 120,
        'modelRequests': calls * 10,
        'visibleTestTools': total * 5,
        'rolloutVerification': total * 5,
        'evaluatorReplay': total * 5,
        'reviewerReplay': total * 5,
        # One calibrated allowance already covers 8 journal/file pairs with 2x
        # sample headroom. Separate setup/publication (4), SDK (1), requests (12),
        # tools (3), three verifiers (6); validate actual fixture counts at runtime.
        'journalAndFiles': math.ceil((total * (4 + 1 + 6 * 2 + 3 + 3 * 2) + 4) * io_seconds),
    }
    maximum = math.ceil(sum(phases.values()))
    if maximum > MAX_SECONDS:
        raise ValueError('GEPA fixture workload exceeds 7200s; inspect storage calibration before dispatch')
    replay = math.ceil(total * (5 + 2 * io_seconds))
    normal = math.ceil(120 + total * (4 + 12 * io_seconds))
    return {'policy': 'gepa-fixture-workload-v2', 'normalSeconds': min(normal, maximum),
            'workflowSeconds': maximum, 'searchEvaluations': 8,
            'finalEvaluations': total - 8, 'maximumRollouts': total,
            'modelRequests': calls, 'visibleTestTools': total,
            'verificationPasses': 3, 'verificationBatches': 3 * total,
            'evaluatorReplays': total, 'reviewReplays': total,
            'phasesSeconds': phases, 'oneReplaySeconds': replay,
            'approvalExtraReplays': 4, 'caseCleanupSeconds': 30}


def case_budget(identifier, io_seconds):
    budget = smoke_budget(io_seconds)
    method = identifier.rsplit('.', 1)[-1]
    extra = budget['approvalExtraReplays'] * budget['oneReplaySeconds'] if method == APPROVAL_CASE else 0
    if method in FULL_CASES:
        maximum = budget['workflowSeconds'] + extra + budget['caseCleanupSeconds']
        normal = budget['normalSeconds'] + extra
    else:
        # Early-failure cases still own a frozen workflow; the supervisor must
        # let that inner deadline and evidence cleanup run. Dataset golden
        # references launch 100 individually bounded trusted subprocesses.
        maximum = (650 + math.ceil(20 * io_seconds) if '.DatasetTests.' in identifier
                   else budget['workflowSeconds'] + budget['caseCleanupSeconds'])
        normal = 30 if '.DatasetTests.' in identifier else 60
    return {'normalSeconds': normal, 'maximumSeconds': maximum, 'extraReplaySeconds': extra}


def module_budget(io_seconds, command, root):
    """Use exact discovery/selection order without importing the SDK."""
    tree = ast.parse((Path(root) / 'tests/gepa_test.py').read_text())
    identifiers = sorted('gepa_test.' + cls.name + '.' + method.name
                         for cls in tree.body if isinstance(cls, ast.ClassDef)
                         for method in cls.body if isinstance(method, ast.FunctionDef)
                         and method.name.startswith('test_'))
    selected = identifiers
    for option in ('--case', '--from-case'):
        if option in command:
            anchor = command[command.index(option) + 1]
            if anchor not in identifiers:
                raise ValueError('Unknown GEPA case: ' + anchor)
            selected = [anchor] if option == '--case' else identifiers[identifiers.index(anchor):]
    if not selected:
        raise ValueError('Empty GEPA workload')
    costs = [case_budget(identifier, io_seconds) for identifier in selected]
    maximum = 30 + sum(row['maximumSeconds'] for row in costs)
    if maximum > MAX_SECONDS:
        raise ValueError('GEPA selected module exceeds 7200s; split into exact --case checks before dispatch')
    return {'selected': selected, 'normalSeconds': sum(row['normalSeconds'] for row in costs),
            'maximumSeconds': maximum}


def expand_plan(plan, root):
    """One supervised GEPA case per step; no aggregate parent can cut off a case."""
    result = []
    for name, command in plan:
        if name == 'python-gepa_test' and '--case' not in command:
            # Discover the manifest before any expensive imports or model work.
            tree = ast.parse((Path(root) / 'tests/gepa_test.py').read_text())
            ids = sorted('gepa_test.' + cls.name + '.' + fn.name
                         for cls in tree.body if isinstance(cls, ast.ClassDef)
                         for fn in cls.body if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_'))
            base = list(command)
            if '--from-case' in base:
                index = base.index('--from-case')
                anchor = base[index + 1]
                if anchor not in ids:
                    raise ValueError('Unknown GEPA case: ' + anchor)
                ids = ids[ids.index(anchor):]
                base = base[:index]
            if not ids:
                raise ValueError('Empty GEPA workload')
            result.extend((name + '--' + identifier, base + ['--case', identifier]) for identifier in ids)
        else:
            result.append((name, list(command)))
    return result
