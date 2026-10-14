"""Frozen project-health checks: explicit scope and shared nested deadlines."""
import ast
import hashlib
import math
from pathlib import Path

MODULES = ('sdk_runtime_probe_test.py', 'setup_orchestrator_test.py', 'setup_test.py',
           'skill_test.py', 'step_trace_test.py')
CHILD_CLEANUP_SECONDS = 30
ROLE_CLEANUP_SECONDS = 35
MODULE_CLEANUP_SECONDS = 50
DEFAULT_ROLE_SECONDS = 120
MAX_SECONDS = 7200


def build(root, calibration=None):
    from adaptive_validation import current, calculate
    from sdk_runtime_probe import PROBE_SECONDS
    root = Path(root)
    calibration = current() if calibration is None else calibration
    measured = calculate(calibration['samplesSeconds'], calibration['inferenceTimeout'])
    io = measured['perCallIoAllowanceSeconds']
    # Allow startup, evidence I/O and teardown per discovered case. SDK import
    # fixtures also reserve two complete isolated-probe deadlines per module.
    per_case = max(30, math.ceil(20 + 20 * io))
    modules = []
    for name in MODULES:
        path = root/'tests'/name
        source = path.read_bytes()
        count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')
                    for n in ast.walk(ast.parse(source)))
        if not count:
            raise ValueError('Empty native check module: ' + name)
        maximum = count * per_case + 60 + (2 * PROBE_SECONDS if name == MODULES[0] else 0)
        if name == 'skill_test.py':
            # The largest case runs two complete five-role tool workflows.
            maximum = max(maximum, 2 * (5 * DEFAULT_ROLE_SECONDS + 15) + 60)
        modules.append({'module': name, 'cases': count, 'sourceHash': hashlib.sha256(source).hexdigest(),
                        'normalSeconds': max(15, math.ceil(10 + count * (2 + 3 * io))),
                        'maximumSeconds': maximum})
    worker = {'normalSeconds': 45, 'maximumSeconds': 180}
    roles = {'coordinator': DEFAULT_ROLE_SECONDS, 'worker': worker['maximumSeconds'] + ROLE_CLEANUP_SECONDS,
             'evaluator': sum(row['maximumSeconds'] + CHILD_CLEANUP_SECONDS for row in modules) + ROLE_CLEANUP_SECONDS,
             'reflector': DEFAULT_ROLE_SECONDS, 'reviewer': DEFAULT_ROLE_SECONDS}
    maximum = sum(roles.values()) + ROLE_CLEANUP_SECONDS
    if maximum > MAX_SECONDS:
        raise ValueError('Native health workload exceeds the bounded 7200-second budget; inspect filesystem calibration')
    return {'schemaVersion': 1, 'scope': 'project-health-explicit-five-modules',
            'calibration': calibration, 'perCaseAllowanceSeconds': per_case, 'modules': modules,
            'worker': worker, 'roleMaximumSeconds': roles,
            'maximumSeconds': maximum, 'childCleanupSeconds': CHILD_CLEANUP_SECONDS,
            'roleCleanupSeconds': ROLE_CLEANUP_SECONDS, 'moduleCleanupSeconds': MODULE_CLEANUP_SECONDS}


def validate(plan, root):
    expected = build(root, plan['calibration'])
    if plan != expected:
        raise ValueError('Frozen native check scope, source, or deadline changed')
    return expected
