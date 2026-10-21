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
SPLIT_MODULES=('gepa_test','challenge_failure_test')
BANK_MODULES=('challenge_workflow_test','challenge_v2_workflow_test','challenge_v3_workflow_test','paired_workflow_test')
INTEGRATION_MODULES=(*BANK_MODULES,'challenge_failure_test','exploration_workflow_test','strata_workflow_test')


def integration_module_budget(name,io_seconds,command,root):
    """Contain delegated SDK workflows and post-completion replays in their parent."""
    module=name.removeprefix('python-').split('--',1)[0]
    if module not in INTEGRATION_MODULES:return None
    if not math.isfinite(io_seconds) or io_seconds<0:raise ValueError('Invalid integration storage calibration')
    from check_start_selection import case_ids
    ids=case_ids(root,module+'.py');selected=ids
    for option in ('--case','--from-case'):
        if option in command:
            anchor=command[command.index(option)+1]
            if anchor not in ids:raise ValueError('Unknown integration case: '+anchor)
            selected=[anchor] if option=='--case' else ids[ids.index(anchor):]
    if not selected:raise ValueError('Empty integration workload')
    passes=3
    if module=='strata_workflow_test':
        if len(ids)!=3:raise ValueError('Strata workflow manifest changed; audit delegated cases')
        from validation_wait import repair_workflow_seconds
        phases={'gepaWithApproval':case_budget('gepa_test.GepaWorkflowTests.'+APPROVAL_CASE,io_seconds)['maximumSeconds'],
                'llmWorkflowAndReplay':math.ceil(15*(10+io_seconds)+30)+60,
                'repairWorkflowAndReplay':repair_workflow_seconds(io_seconds)+30,
                'sdkAdmission':480,'setupAndTeardown':90}
        rollouts=20;extra=4
    elif module=='challenge_failure_test':
        if len(selected)!=1:raise ValueError('Integration module exceeds 7200s; split task-cap cases before dispatch')
        method=selected[0].rsplit('.',1)[-1]
        if '.CapClassificationTests.' in selected[0] and method in (
                'test_late_rollout_publication_cannot_erase_later_calls',
                'test_only_a_complete_local_call_cap_qualifies_and_infrastructure_remains_fatal'):
            phases={'controlledClassification':60};rollouts=0;extra=0
        elif method=='test_last_call_correct_source_is_still_a_failed_task_without_sdk_completion':
            phases={'sdkAdmission':240,'sdkStartup':120,'requests':20,'tools':10,'replays':10,'setupAndTeardown':60}
            rollouts=1;extra=1;passes=1
        elif method in ('test_failed_search_and_final_tasks_score_zero_and_remaining_tail_is_reviewed',
                        'test_http_failure_aborts_without_scoring_zero_or_running_final_tasks'):
            rollouts=22;extra=3 if method.startswith('test_failed_search') else 0
            phases={'workflow':4450,'sdkAdmission':240,'terminalCollection':30,'setupAndTeardown':60,
                    'postCompletionReplay':math.ceil(extra*rollouts*(5+2*io_seconds))}
        else:raise ValueError('Unbudgeted task-cap integration case')
    else:
        if len(ids)!=1:raise ValueError('Integration manifest changed; audit every added workflow')
        rollouts=43 if module=='exploration_workflow_test' else 22
        extra=3 if module=='exploration_workflow_test' else 2 if module=='challenge_workflow_test' else 1
        phases={'workflow':3630 if module=='exploration_workflow_test' else 4450,'sdkAdmission':240,
                'terminalCollection':30,'setupAndTeardown':60+math.ceil(60*io_seconds),
                'postCompletionReplay':math.ceil(extra*rollouts*(5+2*io_seconds))}
    maximum=sum(phases.values())+30
    if maximum>MAX_SECONDS:raise ValueError('Integration fixture workload exceeds 7200s; inspect calibration or split cases')
    return {'policy':'delegated-sdk-workload-v1','selected':selected,'maximumRollouts':rollouts,
            'verificationBatches':passes*rollouts,'postCompletionPasses':extra,'phasesSeconds':phases,
            'normalSeconds':max(60,math.ceil(120+rollouts*(4+12*io_seconds))), 'maximumSeconds':maximum}


def canonical_fixture_budget(io_seconds):
    """Three cases: actual search/replay/approval, paused cancellation and failure."""
    if not math.isfinite(io_seconds) or io_seconds<0:raise ValueError('Invalid canonical storage calibration')
    rollouts=10+2*(3+3);calls=rollouts*6+1
    workflow=120+calls*10+rollouts*(24*5+3*5)+30+8*15
    phases={'sdkAdmission':3*240,'sourceAdmission':3*15,'positiveWorkflow':workflow,
            'approvalReplay':math.ceil(rollouts*(5+2*io_seconds)),
            'controlledChildStartup':20,'pausedFinalizers':35,'terminalCollection':90,
            'setupAndTeardown':90+math.ceil(90*io_seconds)}
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
        if name in tuple('python-'+module for module in SPLIT_MODULES) and '--case' not in command:
            # Discover the manifest before any expensive imports or model work.
            module=name.removeprefix('python-')
            tree = ast.parse((Path(root) / ('tests/'+module+'.py')).read_text())
            ids = sorted(module+'.' + cls.name + '.' + fn.name
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
