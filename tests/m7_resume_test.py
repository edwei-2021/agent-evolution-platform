"""Evidence-scoped continuation and exact case selection regression tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from check_m7_remaining import prior_failure, remaining_plan, build_plan, archive_report
from run_test_module import select_suite
from check_steps import run as run_checks


def suite():
    class Fixture(unittest.TestCase):
        def runTest(self):
            pass
        def id(self):
            return self.description
    result = []
    for name in ('llm_test.C.test_a', 'llm_test.C.test_b', 'llm_test.C.test_c'):
        test = Fixture()
        test.description = name
        result.append(test)
    return unittest.TestSuite([unittest.TestSuite(result)])


class SelectionTests(unittest.TestCase):
    def test_exact_and_remaining_selection_preserve_order_and_omissions(self):
        selected, scope = select_suite(suite(), from_case='llm_test.C.test_b')
        self.assertEqual(selected.countTestCases(), 2)
        self.assertEqual(scope['selected'], ['llm_test.C.test_b', 'llm_test.C.test_c'])
        self.assertEqual(scope['omitted'], ['llm_test.C.test_a'])
        self.assertEqual(select_suite(suite(), case='llm_test.C.test_b')[0].countTestCases(), 1)
    def test_missing_anchor_and_empty_suite_cannot_pass(self):
        for tests, anchor in [(suite(), 'missing'), (unittest.TestSuite(), None)]:
            with self.assertRaises(ValueError):
                select_suite(tests, from_case=anchor)
    def test_tail_excludes_passed_gepa_and_keeps_later_modules(self):
        plan = [('python-gepa_test', ['python', 'runner', 'gepa_test.py']),
                ('python-llm_test', ['python', 'runner', 'llm_test.py']),
                ('python-runtime_test', ['python', 'runner', 'runtime_test.py'])]
        selected, omitted = remaining_plan(plan, 'python-llm_test', 'llm_test.C.test_b')
        self.assertEqual(omitted, ['python-gepa_test'])
        self.assertEqual(selected[0][1][-2:], ['--from-case', 'llm_test.C.test_b'])
        self.assertEqual(selected[-1][0], 'python-runtime_test')
        self.assertEqual(len(plan[1][1]), 3)  # selection cannot mutate the full plan
        with self.assertRaises(ValueError):
            remaining_plan(plan, 'python-llm_test', 'gepa_test.C.test_b')
    def test_second_failure_resumes_monitor_or_type_step_without_model_replay(self):
        release = [('python-gepa_test', ['python', 'runner', 'gepa_test.py']),
                   ('python-llm_test', ['python', 'runner', 'llm_test.py']),
                   ('python-runtime_test', ['python', 'runner', 'runtime_test.py'])]
        prior = {'scope': {'kind': 'm7-remaining', 'fromCase': 'llm_test.C.test_b'}}
        plan, omitted, completed, origin = build_plan(
            release, prior, 'monitor-regressions', 'check_steps_test.C.test_b', 'node')
        self.assertEqual(plan[0][0], 'filesystem-calibration')
        self.assertEqual(plan[1][0], 'monitor-regressions')
        self.assertEqual(plan[1][1][-2:], ['--from-case', 'check_steps_test.C.test_b'])
        self.assertNotIn('python-llm_test', [name for name, _ in plan])
        self.assertIn('python-llm_test', completed)
        self.assertEqual(plan[-1][0], 'm7-types')
        unit = next(command for name, command in plan if name == 'm7-unit')
        self.assertTrue(unit[0].endswith('.venv-m/bin/python'))
        self.assertIn('-s', unit)  # preserve the WSL DrvFS capture fix
        self.assertEqual(origin, 'llm_test.C.test_b')
        self.assertEqual(omitted, ['python-gepa_test'])
        plan, *_ = build_plan(release, prior, 'm7-types', None, 'node')
        self.assertEqual([name for name, _ in plan], ['filesystem-calibration', 'm7-types'])
        with self.assertRaises(ValueError):
            build_plan(release, prior, 'arbitrary-command', None, 'node')
        with self.assertRaises(ValueError):
            build_plan(release, prior, 'monitor-regressions', 'llm_test.C.test_b', 'node')

    def test_strict_gepa_tail_does_not_repeat_passed_prechecks_or_ten_gepa_cases(self):
        perfect = 'gepa_test.GepaWorkflowTests.test_perfect_seed_skips_proposals_and_cannot_release_without_improvement'
        final = 'gepa_test.GepaWorkflowTests.test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate'
        release = [('python-gepa_test', ['python', 'scripts/run_test_module.py', 'gepa_test.py']),
                   ('python-llm_test', ['python', 'scripts/run_test_module.py', 'llm_test.py'])]
        plan, _, _, _ = build_plan(release, {}, 'python-gepa_test', perfect, 'node')
        self.assertEqual([command[-1] for name, command in plan if name.startswith('python-gepa_test--')], [perfect, final])
        names = [name for name, _ in plan]
        self.assertTrue({'native-regressions', 'monitor-regressions', 'frontend-regressions', 'm7-unit'}.isdisjoint(names))
        self.assertEqual(names[-3:], ['m7-source-scan', 'm7-ruff', 'm7-types'])
        prior = {'scope': {'kind':'m7-remaining', 'releaseFromCase':perfect}}
        resumed, _, completed, _ = build_plan(release, prior, 'python-gepa_test--' + final, final, 'node')
        self.assertEqual(resumed[1][1][-2:], ['--case', final])
        self.assertNotIn(perfect, [command[-1] for _, command in resumed])
        self.assertIn('python-gepa_test--' + perfect, completed)

    def test_scoped_type_failure_zip_keeps_provenance_without_inventing_a_case(self):
        report = {'profile': 'release', 'status': 'failed',
                  'scope': {'kind': 'm7-remaining', 'fromCase': 'llm_test.C.test_b'},
                  'steps': [{'step': 'm7-types', 'status': 'failed', 'testCases': []}]}
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)/'support.zip'
            with zipfile.ZipFile(bundle, 'w') as archive:
                archive.writestr('report.json', json.dumps(report))
            prior, step, anchor, digest = prior_failure(bundle)
            self.assertEqual(step, 'm7-types')
            self.assertIsNone(anchor)
            self.assertEqual(prior['scope']['fromCase'], 'llm_test.C.test_b')
            self.assertEqual(len(digest), 64)

    def test_archive_is_scoped_to_its_own_directory_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            own = Path(tmp)/'own'
            other = Path(tmp)/'other'
            own.mkdir();other.mkdir()
            (own/'report.json').write_text(json.dumps({'id': 'own', 'api_key': 'private-value'}))
            (own/'test.log').write_text('password=private-value')
            (other/'test.log').write_text('other run evidence')
            with zipfile.ZipFile(archive_report(own)) as bundle:
                self.assertEqual(set(bundle.namelist()), {'report.json', 'test.log'})
                self.assertNotIn('private-value', bundle.read('report.json').decode())
                self.assertNotIn('private-value', bundle.read('test.log').decode())
                self.assertNotIn('other run evidence', bundle.read('test.log').decode())

    def test_empty_plan_and_invalid_report_identity_cannot_pass_or_escape(self):
        with self.assertRaises(ValueError):
            run_checks('release', plan=[])
        with self.assertRaises(ValueError):
            run_checks('release', plan=[('never', ['never'])], identifier='../outside')

    def test_json_and_zip_prior_evidence_have_identical_anchor(self):
        report = {'id': 'CHECK-prior', 'profile': 'release', 'status': 'failed',
                  'steps': [{'step': 'python-gepa_test', 'status': 'completed'},
                            {'step': 'python-llm_test', 'status': 'failed', 'testCases': [
                                {'test': 'llm_test.C.test_a', 'status': 'passed'},
                                {'test': 'llm_test.C.test_b', 'status': 'error'}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'report.json'
            path.write_text(json.dumps(report))
            bundle = Path(tmp)/'support.zip'
            with zipfile.ZipFile(bundle, 'w') as archive:
                archive.writestr('release/report.json', json.dumps(report))
            self.assertEqual(prior_failure(path)[:3], prior_failure(bundle)[:3])
            self.assertEqual(len(prior_failure(path)[3]), 64)
            report['steps'][-1]['testCases'] = []
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                prior_failure(path)
            report['status'] = 'completed'
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                prior_failure(path)


if __name__ == '__main__':
    unittest.main()
