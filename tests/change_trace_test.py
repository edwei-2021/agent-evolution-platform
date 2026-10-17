"""No-model regressions for actual source history and bounded read-only HTTP."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from change_trace import snapshot
from serve_gui import GuiHandler, DIST

BASE = 'def clamp(value, lower, upper):\n    return value\n'
FIRST = 'def clamp(value, lower, upper):\n    return min(value, upper)\n'
SECOND = 'def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n'


class Service:
    def __init__(self, root, task='nanobot-repair', status='failed'):
        self.root = Path(root)
        self.local = self.root / '.local'
        self.run = {'id': 'RUN-history', 'task': task, 'status': status}
        self.directory = self.local / 'runs' / self.run['id']
        self.directory.mkdir(parents=True)

    def get_run(self, identifier):
        if identifier != self.run['id']:
            raise KeyError('Unknown Run')
        return self.run


def save(directory, name, value):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value)


def prepare(directory):
    save(directory, 'repair-config.json', {'taskId': 'PY-history', 'skill': {'body': 'Read, repair and test.', 'hash': 'a' * 64},
                                          'provider': {'apiKey': 'PRIVATE_CONFIG_KEY'},
                                          'fixture': {'prompt': 'Repair the inclusive bounds.', 'hidden': ['PRIVATE_HIDDEN_TEST']}})
    save(directory, 'repair-baseline.py', BASE)
    tools = [
        {'id': 1, 'name': 'read_solution', 'status': 'completed', 'arguments': {'path': 'solution.py'}, 'result': BASE},
        {'id': 2, 'name': 'write_solution', 'status': 'completed', 'arguments': {'path': 'solution.py', 'source': FIRST}},
        {'id': 3, 'name': 'run_tests', 'status': 'completed', 'arguments': {}, 'result': json.dumps({'passed': 2, 'total': 3})},
        {'id': 4, 'name': 'write_solution', 'status': 'failed', 'arguments': {'path': 'solution.py', 'source': SECOND}, 'error': 'Rejected write'},
        {'id': 5, 'name': 'write_solution', 'status': 'completed', 'arguments': {'path': 'solution.py', 'source': FIRST}},
        {'id': 6, 'name': 'write_solution', 'status': 'completed', 'arguments': {'path': 'solution.py', 'source': SECOND}},
        {'id': 7, 'name': 'run_tests', 'status': 'completed', 'arguments': {}, 'result': json.dumps({'passed': 3, 'total': 3})},
    ]
    save(directory, 'repair-tools.json', tools)


class ChangeHistoryTests(unittest.TestCase):
    def test_large_frozen_bank_config_keeps_skill_history_and_excludes_dataset_contents(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root,task='gepa-evolution')
            cfg={'baseline':{'skill':{'body':'Frozen bank Skill','hash':'a'*64}},
                 'datasetSnapshot':{'privateFixture':'PRIVATE_BANK_CASE'*15000}}
            save(service.directory,'gepa-config.json',cfg)
            self.assertGreater((service.directory/'gepa-config.json').stat().st_size,128000)
            result=snapshot(service,'RUN-history')
            self.assertEqual(result['skillHistory'][0]['before'],'Frozen bank Skill')
            self.assertNotIn('PRIVATE_BANK_CASE',json.dumps(result))
            self.assertEqual(result['warnings'],[])

    def test_every_success_failed_write_unchanged_write_and_test_keeps_its_actual_source(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            prepare(service.directory)
            with patch('subprocess.run', side_effect=AssertionError('No execution permitted')):
                result = snapshot(service, 'RUN-history')
            trace = result['trace']
            self.assertFalse(result['verified'])
            self.assertEqual(trace['baseline'], BASE)
            self.assertEqual(trace['currentSource'], SECOND)
            self.assertIsNone(trace['candidate'])
            steps = trace['steps']
            self.assertEqual(len(steps), 7)
            self.assertEqual(steps[1]['before'], BASE)
            self.assertEqual(steps[1]['after'], FIRST)
            self.assertIn('-    return value', steps[1]['patch'])
            self.assertEqual(steps[2]['visiblePassed'], 2)
            self.assertFalse(steps[3]['applied'])
            self.assertEqual(steps[3]['attemptedSource'], SECOND)
            self.assertEqual(steps[3]['after'], FIRST)
            self.assertFalse(steps[4]['changed'])
            self.assertEqual(steps[5]['before'], FIRST)
            self.assertEqual(steps[5]['after'], SECOND)
            self.assertEqual(steps[6]['visiblePassed'], 3)
            self.assertIn('Fixed Skill', result['skillHistory'][0]['note'])
            self.assertNotIn('PRIVATE_CONFIG_KEY', json.dumps(result))
            self.assertNotIn('PRIVATE_HIDDEN_TEST', json.dumps(result))

    def test_missing_baseline_and_partial_json_do_not_invent_changes_or_success(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root, status='running')
            save(service.directory, 'repair-tools.json', '[{"unfinished":')
            result = snapshot(service, 'RUN-history')
            self.assertIsNone(result['trace']['baseline'])
            self.assertEqual(result['trace']['steps'], [])
            self.assertFalse(result['verified'])
            self.assertTrue(result['warnings'])

    def test_completed_but_unreviewed_snapshot_is_not_verified_and_read_does_not_change_files(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root, status='completed')
            prepare(service.directory)
            save(service.directory, 'repair-candidate.py', SECOND)
            before = {p: p.read_bytes() for p in service.directory.rglob('*') if p.is_file()}
            result = snapshot(service, 'RUN-history')
            self.assertFalse(result['verified'])
            self.assertTrue(result['trace']['candidateMatchesTrace'])
            service.run['repairResult'] = {'checksPassed': True}
            self.assertTrue(snapshot(service, 'RUN-history')['verified'])
            self.assertEqual(before, {p: p.read_bytes() for p in service.directory.rglob('*') if p.is_file()})

    def gepa(self, service):
        service.run['task'] = 'gepa-evolution'
        save(service.directory, 'gepa-config.json', {'baseline': {'skill': {'body': 'Baseline Skill'}}})
        save(service.directory, 'gepa-rollouts.json', [{'id': 'R0001', 'stage': 'search', 'taskId': 'PY-first', 'body': 'Baseline Skill', 'score': 0}])
        prepare(service.directory / 'rollouts' / 'R0001')
        prepare(service.directory / 'rollouts' / 'R0002')  # Interrupted, absent from completed ledger.
        save(service.directory, 'gepa-proposals.json', [
            {'id': 'P001', 'parentBody': 'Baseline Skill', 'body': 'Baseline Skill'},
            {'id': 'P002', 'parentBody': 'Baseline Skill', 'body': 'Improved Skill'}])

    def test_gepa_incomplete_rollout_and_same_body_proposal_are_visible_before_selection(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            self.gepa(service)
            result = snapshot(service, 'RUN-history', 'R0002')
            self.assertEqual(result['selectedRollout'], 'R0002')
            self.assertEqual(result['totalRollouts'], 2)
            self.assertFalse(result['rollouts'][1]['completed'])
            self.assertIsNone(result['rollouts'][1]['score'])
            self.assertFalse(result['skillHistory'][1]['changed'])
            self.assertTrue(result['skillHistory'][2]['changed'])
            self.assertEqual(result['skillHistory'][-1]['kind'], 'pending')
            self.assertFalse(result['verified'])

    def test_selected_rejected_and_unchanged_skill_events_follow_persisted_search(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            self.gepa(service)
            save(service.directory, 'gepa-search.json', {'candidates': [{'skill_body': 'Baseline Skill'}, {'skill_body': 'Improved Skill'}], 'validationScores': [0.5, 1.0]})
            save(service.directory, 'gepa-selection.json', {'skill': {'body': 'Improved Skill'}})
            result = snapshot(service, 'RUN-history')
            proposals = result['skillHistory'][1:3]
            self.assertEqual(proposals[0]['note'], 'Not selected')
            self.assertEqual(proposals[1]['validationScore'], 1.0)
            self.assertEqual(proposals[1]['note'], 'Matches selected Skill')
            self.assertTrue(result['skillHistory'][-1]['changed'])
            save(service.directory, 'gepa-selection.json', {'skill': {'body': 'Baseline Skill'}})
            self.assertFalse(snapshot(service, 'RUN-history')['skillHistory'][-1]['changed'])

    def test_pagination_and_invalid_or_cross_run_rollouts_are_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            self.gepa(service)
            for i in range(3, 26):
                (service.directory / 'rollouts' / f'R{i:04d}').mkdir()
            result = snapshot(service, 'RUN-history', offset=20)
            self.assertEqual(len(result['rollouts']), 5)
            self.assertEqual(result['selectedRollout'], 'R0021')
            for kwargs in ({'rollout': '../../outside'}, {'offset': -1}, {'limit': 21}):
                with self.assertRaises(ValueError):
                    snapshot(service, 'RUN-history', **kwargs)
            with self.assertRaises(KeyError):
                snapshot(service, 'RUN-history', 'R9999')
            with self.assertRaises(KeyError):
                snapshot(service, 'RUN-other')

    def test_symlink_directory_file_fifo_and_oversize_source_never_escape_or_block(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            outside = Path(root) / 'outside'
            outside.write_text('PRIVATE_OUTSIDE')
            target = service.directory / 'repair-baseline.py'
            target.symlink_to(outside)
            with self.assertRaises(ValueError):
                snapshot(service, 'RUN-history')
            target.unlink()
            os.mkfifo(target)
            with self.assertRaises(ValueError):
                snapshot(service, 'RUN-history')
            target.unlink()
            target.write_text('x' * 8001)
            result = snapshot(service, 'RUN-history')
            self.assertIsNone(result['trace']['baseline'])
            self.assertTrue(result['warnings'])
            target.unlink()
            self.gepa(service)
            child = service.directory / 'rollouts' / 'R0003'
            child.symlink_to(Path(root), target_is_directory=True)
            with self.assertRaises(ValueError):
                snapshot(service, 'RUN-history', 'R0003')

    def test_actual_http_route_checks_origin_identity_and_query_without_model_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(root)
            prepare(service.directory)
            class Quiet(GuiHandler):
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(DIST)))
            server.runtime = service
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = '/api/v1/debug/changes/'
                for path, headers, status in [(base + 'RUN-history', {}, 200),
                                              (base + 'RUN-history', {'Origin': 'https://outside.invalid'}, 403),
                                              (base + 'RUN-unknown', {}, 404),
                                              (base + 'RUN-history?offset=0&offset=1', {}, 503),
                                              (base + 'RUN-history?rollout=../../outside', {}, 503)]:
                    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    connection.request('GET', path, headers=headers)
                    response = connection.getresponse()
                    data = json.loads(response.read())
                    connection.close()
                    self.assertEqual(response.status, status)
                    if status == 200:
                        self.assertEqual(len(data['trace']['steps']), 7)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == '__main__':
    unittest.main()
