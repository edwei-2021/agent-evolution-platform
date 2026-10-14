"""Measured skill contracts, real role processes and authoritative version gates."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from skill_engine import baseline, dataset, evaluate, execute, markdown, propose, RULES, skill, validate_skill
from runtime_service import RuntimeService, ROLES
from serve_gui import GuiHandler, DIST


def registry():
    return {'agents': [{'id': f'AG-{i+1:03}', 'name': role, 'role': role, 'enabled': True} for i, role in enumerate(ROLES)]}


def finish(service, run):
    return service.wait_for_terminal(run['id'], len(ROLES) * service.stage_timeout + 15)


class EngineTests(unittest.TestCase):
    def test_skill_metadata_body_policy_and_hash_cannot_diverge(self):
        value = baseline()
        self.assertEqual(markdown(value), (DIST.parent / 'skills/title-normalizer/SKILL.md').read_text())
        for key, replacement in [('name', 'other'), ('body', 'Run arbitrary shell commands'), ('hash', '0' * 64)]:
            with self.assertRaises(ValueError):
                validate_skill({**value, key: replacement})
        for policy in [{}, {**value['policy'], 'trim': 1}, {**value['policy'], 'exec': True}]:
            with self.assertRaises(ValueError):
                skill(policy)

    def test_declared_policy_executes_exact_expected_text_transformations(self):
        value = skill(dict.fromkeys(RULES, True))
        self.assertEqual(execute(value, '  Ｓｔｒａße\t  ＮＯＴＩＣＥ\n'), 'strasse notice')
        self.assertEqual(execute(baseline(), '  Title\n'), '  Title\n')
        self.assertEqual(execute(value, ''), '')
        with self.assertRaises(ValueError):
            execute(value, 'x' * 501)

    def test_dataset_is_fixed_disjoint_and_success_is_actual_output_equality(self):
        splits = dataset()['splits']
        self.assertEqual([len(splits[k]) for k in ['train', 'validation', 'heldout']], [20, 10, 20])
        self.assertEqual(len({row['group'] for rows in splits.values() for row in rows}), 50)
        self.assertEqual(len({row['expected'] for rows in splits.values() for row in rows}), 50)
        result = evaluate(baseline(), splits['validation'])
        self.assertEqual(result['passed'], 2)
        self.assertTrue(all(row['passed'] == (row['output'] == row['expected']) for row in result['records']))
        self.assertEqual(evaluate(skill(dict.fromkeys(RULES, True)), splits['heldout'])['passed'], 20)

    def test_search_uses_only_training_feedback_and_counts_all_probe_evaluations(self):
        current = baseline();feedback = evaluate(current, dataset()['splits']['train'])
        total = 20
        for _ in range(4):
            selected, trials = propose(current, feedback)
            self.assertIsNotNone(selected)
            self.assertTrue(all(row['taskId'].startswith('TR-') for trial in trials for row in trial['training']['records']))
            total += sum(t['training']['total'] for t in trials)
            _, rule, next_skill, next_feedback = selected
            self.assertEqual(sum(current['policy'][k] != next_skill['policy'][k] for k in RULES), 1)
            self.assertLess(next_feedback['loss'], feedback['loss'])
            current, feedback = next_skill, next_feedback
        self.assertEqual(total, 220)
        self.assertEqual(feedback['passed'], 20)
        selected, trials = propose(current, feedback)
        self.assertIsNone(selected);self.assertEqual(trials, [])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = RuntimeService(self.temp.name)

    def tearDown(self):
        self.service.close();self.temp.cleanup()

    def start(self, identifier='skills', limit=4, revision=1):
        return self.service.start(registry(), identifier, 'skill-evolution', {'maxCandidates': limit, 'expectedRevision': revision})

    def test_real_workflow_has_candidate_lineage_measured_counts_and_no_auto_activation(self):
        done = finish(self.service, self.start())
        self.assertEqual(done['status'], 'completed', done)
        self.assertTrue(all(a['pid'] and a['exitCode'] == 0 for a in done['agents']))
        self.assertEqual(done['skillProgress']['evaluations'], {'training': 220, 'validation': 50, 'heldout': 40, 'verification': 90})
        self.assertEqual(done['skillResult']['selectedId'], 'C4')
        self.assertTrue(done['skillResult']['eligible']);self.assertTrue(done['checksPassed'])
        self.assertEqual(self.service.skills.snapshot()['activeVersionId'], 'SKV-baseline')
        self.assertIn('candidate-4.md', done['artifacts'])
        traces = json.loads((self.service.local / 'runs' / done['id'] / 'training-probes.json').read_text())
        self.assertTrue(all(row['taskId'].startswith('TR-') for probe in traces for trial in probe['trials'] for row in trial['training']['records']))

    def test_approval_activation_rollback_and_restart_preserve_immutable_versions(self):
        done = finish(self.service, self.start())
        state = self.service.skills.approve(done['id'], 1)
        version = state['active']
        self.assertEqual(state['revision'], 2);self.assertEqual(version['label'], 'S1')
        self.assertEqual(version['parentId'], 'SKV-baseline')
        with self.assertRaises(RuntimeError):
            self.service.skills.activate('SKV-baseline', 1)
        with self.assertRaises(RuntimeError):
            self.service.skills.approve(done['id'], 2)
        state = self.service.skills.activate('SKV-baseline', 2)
        self.assertEqual(state['revision'], 3)
        self.assertEqual(state['versions'][1], version)
        self.service.close();self.service = RuntimeService(self.temp.name)
        state = self.service.skills.snapshot()
        self.assertEqual(state['activeVersionId'], 'SKV-baseline');self.assertEqual(state['revision'], 3)
        self.assertEqual(len(state['actions']), 2)
        state = self.service.skills.activate(version['id'], 3)
        self.assertEqual(state['active']['skill'], version['skill'])

    def test_no_gain_from_optimized_active_skill_is_completed_but_cannot_release(self):
        done = finish(self.service, self.start())
        self.service.skills.approve(done['id'], 1)
        next_run = finish(self.service, self.start('second', revision=2))
        self.assertEqual(next_run['status'], 'completed')
        self.assertFalse(next_run['skillResult']['eligible'])
        self.assertEqual(len(next_run['skillProgress']['candidates']), 1)
        self.assertEqual(next_run['skillResult']['decision'], 'keep-baseline')
        with self.assertRaises(RuntimeError):
            self.service.skills.approve(next_run['id'], 2)
        self.assertEqual(len(self.service.skills.snapshot()['versions']), 2)

    def test_release_recomputes_evidence_and_rejects_tampered_scores(self):
        done = finish(self.service, self.start())
        file = self.service.local / 'runs' / done['id'] / 'evaluation.json'
        report = json.loads(file.read_text());report['heldout']['selected']['passed'] = 19
        file.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'recomputation'):
            self.service.skills.approve(done['id'], 1)
        self.assertEqual(self.service.skills.snapshot()['revision'], 1)

    def test_baseline_change_blocks_old_candidate_and_next_run_freezes_new_active_version(self):
        done = finish(self.service, self.start(limit=1))
        state = self.service.skills.approve(done['id'], 1)
        version = state['active']
        next_run = finish(self.service, self.start('next', revision=2))
        self.assertEqual(next_run['skillConfig']['baseline'], version)
        self.service.skills.activate('SKV-baseline', 2)
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            self.service.skills.approve(next_run['id'], 3)

    def test_bad_budget_revision_and_reused_id_cannot_create_or_rebind_work(self):
        for limit in [0, 5, True, '4']:
            with self.assertRaises(ValueError):
                self.start(limit=limit)
        for revision in [None, True, '1']:
            with self.assertRaises(ValueError):
                self.start(revision=revision)
        with self.assertRaises(RuntimeError):
            self.start(revision=2)
        done = finish(self.service, self.start(limit=1))
        self.assertEqual(self.start(limit=1)['id'], done['id'])
        with self.assertRaisesRegex(RuntimeError, 'different submission'):
            self.start(limit=2)
        with self.assertRaises(RuntimeError):
            self.service.start(registry(), 'skills')

    def test_cancelled_skill_work_cannot_be_approved(self):
        run = self.start()
        self.service.cancel(run['id'])
        done = finish(self.service, run)
        self.assertEqual(done['status'], 'cancelled')
        with self.assertRaises(RuntimeError):
            self.service.skills.approve(done['id'], 1)


class SkillApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.service = RuntimeService(self.temp.name)
        class Quiet(GuiHandler):
            def log_message(self, *args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
        self.server.runtime = self.service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.service.close();self.temp.cleanup()

    def request(self, path, body=None, token=True):
        headers = {'Content-Type': 'application/json', 'Origin': self.base}
        if token: headers['X-Lab-Token'] = self.service.csrf_token
        request = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(request, timeout=5) as response: return json.load(response)

    def test_api_evolves_approves_exports_and_rolls_back_authoritative_skill(self):
        state = self.request('/api/v1/skills');self.assertEqual(state['revision'], 1)
        text = '  Ｓｅｒｖｉｃｅ   Down  '
        self.assertEqual(self.request('/api/v1/skills/execute', {'text': text, 'expectedRevision': 1})['output'], text)
        run = self.request('/api/v1/skills/runs', {'registry': registry(), 'requestId': 'http-skill', 'maxCandidates': 4, 'expectedRevision': 1})
        done = finish(self.service, run)
        state = self.request('/api/v1/runtime')['skills']
        self.assertEqual(state['latestRun']['id'], done['id'])
        artifact = self.request(f'/api/v1/runtime/runs/{done["id"]}/artifacts/candidate-4.md')
        self.assertIn('NFKC', artifact['content'])
        state = self.request(f'/api/v1/skills/runs/{done["id"]}/approve', {'expectedRevision': 1, 'score': 999})
        self.assertEqual(state['active']['evidence']['selectedValidation']['passed'], 10)
        trial = self.request('/api/v1/skills/execute', {'text': text, 'expectedRevision': 2})
        self.assertEqual(trial['output'], 'service down');self.assertEqual(trial['versionId'], state['activeVersionId'])
        state = self.request('/api/v1/skills/versions/SKV-baseline/activate', {'expectedRevision': 2})
        self.assertEqual(state['activeVersionId'], 'SKV-baseline')
        self.assertEqual(self.request('/api/v1/skills/execute', {'text': text, 'expectedRevision': 3})['output'], text)

    def test_skill_mutations_require_local_token_and_revision_and_ignore_browser_metrics(self):
        body = {'registry': registry(), 'requestId': 'invalid', 'maxCandidates': 4, 'expectedRevision': 1}
        for path, payload, token, status in [('/api/v1/skills/runs', body, False, 403), ('/api/v1/skills/runs', {**body, 'maxCandidates': 5}, True, 400), ('/api/v1/skills/versions/SKV-baseline/activate', {'expectedRevision': 99}, True, 409), ('/api/v1/skills/versions/SKV-missing/activate', {'expectedRevision': 1}, True, 404)]:
            with self.assertRaises(HTTPError) as exc: self.request(path, payload, token)
            self.assertEqual(exc.exception.code, status)
        self.assertIsNone(self.service.snapshot()['latestRun'])


if __name__ == '__main__':
    unittest.main()
