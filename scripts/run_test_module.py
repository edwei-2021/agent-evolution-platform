#!/usr/bin/env python3
"""Run one unittest module with flushed per-case progress and timings."""
import argparse
import json
from pathlib import Path
import sys
import signal
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
GEPA_FULL_CASES = ('test_actual_js_client_to_python_api_dispatch_and_result_validation',
                   'test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate',
                   'test_perfect_seed_skips_proposals_and_cannot_release_without_improvement',
                   'test_heldout_regression_blocks_release_even_with_validation_improvement')


class ModuleInterrupted(BaseException):
    """Cancellation must bypass transport/tool handlers for ordinary errors."""


def expected_case_seconds(identifier):
    if not identifier.startswith('gepa_test.'):
        return None
    if '.DatasetTests.' in identifier:
        return 30
    if identifier.rsplit('.', 1)[-1] not in GEPA_FULL_CASES:
        return 60
    from gepa_validation_budget import smoke_budget
    try:
        report=json.loads((ROOT/'.local/test-reports/validation-calibration.json').read_text())
        io=float(report['perCallIoAllowanceSeconds'])
    except (OSError,ValueError,TypeError,KeyError):
        from adaptive_validation import current
        io=float(current()['perCallIoAllowanceSeconds'])
    return smoke_budget(io)['normalSeconds']


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = {}
        self.outcomes = {}
        self.case_results = []

    def startTest(self, test):
        key = test.id()
        self.started[key] = time.monotonic()
        normal=expected_case_seconds(key)
        if normal is not None:
            print('TEST_CASE_EXPECTED ' + json.dumps({'test':key,'normalSeconds':normal},ensure_ascii=False),flush=True)
        print('TEST_CASE_STARTED ' + json.dumps({'test': key}, ensure_ascii=False), flush=True)
        super().startTest(test)

    def addSuccess(self, test):
        self.outcomes[test.id()] = 'passed'
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.outcomes[test.id()] = 'failed'
        super().addFailure(test, err)

    def addError(self, test, err):
        self.outcomes[test.id()] = 'error'
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = 'skipped'
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.outcomes[test.id()] = 'expected_failure'
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = 'unexpected_success'
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:self.outcomes[test.id()] = 'failed'
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        key = test.id()
        result = {'test': key, 'status': self.outcomes.get(key, 'unknown'),
                  'durationMs': round((time.monotonic() - self.started.pop(key, time.monotonic())) * 1000, 3)}
        self.case_results.append(result)
        print('TEST_CASE_RESULT ' + json.dumps(result, ensure_ascii=False), flush=True)
        super().stopTest(test)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('pattern', help='one unittest filename pattern, e.g. llm_test.py')
    parser.add_argument('--tests-dir', type=Path, default=Path('tests'))
    args = parser.parse_args(argv)
    if Path(args.pattern).name != args.pattern or not args.pattern.endswith('_test.py'):
        parser.error('pattern must be a single *_test.py filename')
    tests_dir = args.tests_dir.resolve()
    if not tests_dir.is_dir():
        parser.error(f'tests directory does not exist: {tests_dir}')
    sys.path.insert(0, str(tests_dir))
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern=args.pattern,
                                                top_level_dir=str(tests_dir))
    # A release gate only needs the first failing case to block the next step.
    # Continuing after a bounded workflow timeout can add minutes without
    # improving the evidence for that first failure.
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2,
                                     resultclass=TimedResult, failfast=True)
    def interrupt_module(signum, frame):
        # unittest records this as an error and runs tearDown, allowing active
        # SDK workers to be cancelled and failure evidence to be preserved.
        raise ModuleInterrupted('Test module interrupted by '+signal.Signals(signum).name)
    previous = signal.signal(signal.SIGTERM, interrupt_module)
    try:
        result = runner.run(suite)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print('TEST_MODULE_RESULT ' + json.dumps({
        'pattern': args.pattern, 'testsRun': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
        'cases': result.case_results,
    }, ensure_ascii=False), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
