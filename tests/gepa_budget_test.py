"""Workload invariants, phase costs and exact failed-tail supervision."""
import math
import io
import json
import tempfile
from contextlib import redirect_stdout
from unittest.mock import patch
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from gepa_validation_budget import smoke_budget, case_budget, module_budget, expand_plan, APPROVAL_CASE, canonical_fixture_budget

PERFECT = 'gepa_test.GepaWorkflowTests.test_perfect_seed_skips_proposals_and_cannot_release_without_improvement'
APPROVAL = 'gepa_test.GepaWorkflowTests.' + APPROVAL_CASE


class GepaBudgetTests(unittest.TestCase):
    def test_canonical_parent_contains_all_three_cases_and_replays(self):
        import check_steps
        from adaptive_validation import calculate
        budget=canonical_fixture_budget(2)
        self.assertEqual(budget['maximumRollouts'],22)
        self.assertEqual(budget['modelRequests'],133)
        self.assertEqual(budget['verificationBatches'],66)
        self.assertEqual(budget['approvalBatches'],22)
        self.assertEqual(budget['workflowSeconds'],4570)
        self.assertEqual(budget['maximumSeconds'],sum(budget['phasesSeconds'].values()))
        self.assertLessEqual(budget['maximumSeconds'],7200)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            plan=[('python-canonical_workflow_test',[sys.executable,'-c','print("canonical budget probe")'])]
            with patch('check_steps.ROOT',root),patch('adaptive_validation.current',return_value=calculate([.25])),redirect_stdout(io.StringIO()):
                self.assertEqual(check_steps.run('release',plan=plan,interactive=False),0)
            row=json.loads(next((root/'.local/test-reports').glob('CHECK-*/report.json')).read_text())['steps'][0]
            self.assertGreaterEqual(row['maximumSeconds'],budget['workflowSeconds']+budget['phasesSeconds']['sdkAdmission'])
            self.assertEqual(row['gepaCaseBudget']['verificationBatches'],66)
        with self.assertRaises(ValueError):canonical_fixture_budget(100)

    def test_each_rollout_is_verified_three_times_not_once(self):
        budget = smoke_budget(2)
        self.assertEqual(budget['maximumRollouts'], 20)
        self.assertEqual(budget['finalEvaluations'], 12)
        self.assertEqual(budget['verificationBatches'], 60)
        self.assertEqual(budget['modelRequests'], 122)
        phases = budget['phasesSeconds']
        for name in ('rolloutVerification', 'evaluatorReplay', 'reviewerReplay', 'visibleTestTools'):
            self.assertEqual(phases[name], 20 * 5)
        self.assertEqual(budget['workflowSeconds'], sum(phases.values()))
        self.assertEqual(phases['modelRequests'], 122 * 10)
        # Old formula (400s at io=2) omitted enforceable work, not just margin.
        self.assertGreater(phases['modelRequests'] + phases['reviewerReplay'], 400)

    def test_approval_case_reserves_all_four_post_completion_replays(self):
        budget = smoke_budget(2)
        perfect = case_budget(PERFECT, 2)
        approval = case_budget(APPROVAL, 2)
        self.assertEqual(approval['extraReplaySeconds'], 4 * 20 * (5 + 2 * 2))
        self.assertEqual(approval['maximumSeconds'] - perfect['maximumSeconds'], approval['extraReplaySeconds'])
        self.assertEqual(perfect['maximumSeconds'], budget['workflowSeconds'] + 30)

    def test_tail_contains_only_failed_and_unexecuted_gepa_cases(self):
        plan = [('python-gepa_test', ['python', 'runner', 'gepa_test.py', '--from-case', PERFECT]),
                ('python-llm_test', ['python', 'runner', 'llm_test.py'])]
        expanded = expand_plan(plan, ROOT)
        self.assertEqual([command[-1] for _, command in expanded[:-1]], [PERFECT, APPROVAL])
        self.assertEqual(expanded[-1], plan[-1])
        self.assertEqual(expand_plan(expanded, ROOT), expanded)
        total = module_budget(2, plan[0][1], ROOT)
        self.assertEqual(total['selected'], [PERFECT, APPROVAL])
        self.assertEqual(total['maximumSeconds'], 30 + sum(case_budget(case, 2)['maximumSeconds'] for case in (PERFECT, APPROVAL)))
        for _, command in expanded[:-1]:
            limits = module_budget(2, command, ROOT)
            self.assertGreater(limits['maximumSeconds'], smoke_budget(2)['workflowSeconds'])
            self.assertLessEqual(limits['maximumSeconds'], 7200)

    def test_full_module_is_split_before_parent_cap_and_rejects_unsafe_aggregate(self):
        expanded = expand_plan([('python-gepa_test', ['python', 'runner', 'gepa_test.py'])], ROOT)
        self.assertEqual(len(expanded), 14)
        self.assertEqual(len({name for name, _ in expanded}), 14)
        self.assertIn('gepa_test.GepaWorkflowTests.test_malformed_second_proposal_preserves_first_error_without_sdk_retry_or_final_tasks',
                      [command[-1] for _,command in expanded])
        for name, _ in expanded:
            self.assertFalse(set(name) & set('<>:"/\\|?*'))
            self.assertLess(len(name + '.log'), 255)
        for _, command in expanded:
            self.assertLessEqual(module_budget(2, command, ROOT)['maximumSeconds'], 7200)
        with self.assertRaises(ValueError):
            module_budget(2, ['python', 'runner', 'gepa_test.py'], ROOT)

    def test_parent_and_child_share_frozen_calibration_and_case_containment(self):
        import check_steps
        from adaptive_validation import calculate
        frozen = calculate([.25])
        script = ("import json,sys;sys.path.insert(0," + repr(str(ROOT/'scripts')) + ");"
                  "from adaptive_validation import current;from gepa_validation_budget import smoke_budget;"
                  "print('CHILD_CALIBRATION '+json.dumps(current()));"
                  "print('CHILD_BUDGET '+json.dumps(smoke_budget(current()['perCallIoAllowanceSeconds'])))")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'tests').mkdir()
            (root/'tests/gepa_test.py').write_text('class GepaWorkflowTests:\n def '+PERFECT.rsplit('.',1)[-1]+'(self): pass\n')
            plan = [('filesystem-calibration', [sys.executable, '-c', 'print("Frozen calibration")']),
                    ('python-gepa_test', [sys.executable, '-c', script, '--case', PERFECT])]
            with patch('check_steps.ROOT', root), patch('adaptive_validation.current', return_value=frozen), redirect_stdout(io.StringIO()):
                self.assertEqual(check_steps.run('release', plan=plan, interactive=False), 0)
            report = json.loads(next((root/'.local/test-reports').glob('CHECK-*/report.json')).read_text())
            row = report['steps'][-1]
            log = next((root/'.local/test-reports').glob('CHECK-*/python-gepa_test.log')).read_text()
            calibration = json.loads(next(line.split(' ',1)[1] for line in log.splitlines() if line.startswith('CHILD_CALIBRATION ')))
            child = json.loads(next(line.split(' ',1)[1] for line in log.splitlines() if line.startswith('CHILD_BUDGET ')))
            self.assertEqual(calibration['samplesSeconds'], frozen['samplesSeconds'])
            self.assertEqual(calibration['perCallIoAllowanceSeconds'], row['validationCalibration']['perCallIoAllowanceSeconds'])
            self.assertGreaterEqual(row['maximumSeconds'], child['workflowSeconds'] + 60)
            self.assertEqual(row['gepaCaseBudget']['selected'], [PERFECT])

    def test_unsafe_case_budget_is_rejected_before_any_child_is_dispatched(self):
        import check_steps
        from adaptive_validation import calculate
        from unittest.mock import Mock
        launch = Mock(side_effect=AssertionError('Must not dispatch an unsafe budget'))
        with patch('adaptive_validation.current', return_value=calculate([2])), patch('check_steps.subprocess.Popen', launch):
            with self.assertRaisesRegex(ValueError, 'exceeds 7200s'):
                check_steps.run('release', plan=[('python-gepa_test', ['python', 'runner', 'gepa_test.py', '--case', PERFECT])])
        launch.assert_not_called()

    def test_outer_monitor_manifest_matches_expanded_release_steps(self):
        sys.path.insert(0, str(ROOT))
        from platform_m.gates import release_step_count
        modules = [('python-' + path.stem, []) for path in sorted((ROOT/'tests').glob('*_test.py'))]
        self.assertEqual(release_step_count(ROOT), 2 + len(modules) + 13)
        self.assertEqual(release_step_count(ROOT), 2 + len(expand_plan(modules, ROOT)))

    def test_invalid_or_excessive_calibration_and_unknown_case_fail_before_dispatch(self):
        for value in (float('nan'), float('inf'), -1, 100):
            with self.subTest(value=value), self.assertRaises(ValueError):
                smoke_budget(value)
        with self.assertRaises(ValueError):
            module_budget(2, ['--case', 'gepa_test.C.missing'], ROOT)
        with self.assertRaises(ValueError):
            expand_plan([('python-gepa_test', ['--from-case', 'gepa_test.C.missing'])], ROOT)
        for io_seconds in (0, 1.6926176800043322, 2.193912688002456):
            budget = smoke_budget(io_seconds)
            self.assertEqual(budget['workflowSeconds'], math.ceil(sum(budget['phasesSeconds'].values())))


if __name__ == '__main__':
    unittest.main()
