"""Staged check plans preserve the release gate and persist failure evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_steps

class CheckStepsTests(unittest.TestCase):
    def test_quick_plan_and_release_sdk_requirement(self):
        with patch('check_steps.find_node',return_value={'path':'node'}),patch('check_steps.sdk_status',return_value={'available':False}):
            steps=check_steps.stages('quick');self.assertEqual([s[0] for s in steps],['trace','evaluator','frontend'])
            with self.assertRaises(RuntimeError):check_steps.stages('release')
        with patch('check_steps.find_node',return_value={'path':'node'}),patch('check_steps.sdk_status',return_value={'available':True,'python':'sdk-python'}),patch('check_steps.gepa_status',return_value={'available':True}):
            plan=check_steps.stages('release');self.assertEqual(len(plan),2);self.assertIn('*_test.py',plan[1][1]);self.assertEqual(plan[1][1][0],'sdk-python')
    def test_success_report_has_each_started_and_completed_step(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),patch('check_steps.stages',return_value=[('one',[sys.executable,'-c','print("PASS one")']),('two',[sys.executable,'-c','print("PASS two")'])]):
            self.assertEqual(check_steps.run('quick'),0);path=next(Path(root).glob('.local/test-reports/*/report.json'));data=json.loads(path.read_text())
            self.assertEqual(data['status'],'completed');self.assertEqual(len(data['steps']),2)
            self.assertTrue(all(s['startedAt'] and s['finishedAt'] and s['durationMs']>=0 for s in data['steps']))
            self.assertIn('PASS one',(path.parent/'one.log').read_text())
    def test_failure_stops_next_stage_and_preserves_stdout_and_exit_code(self):
        with tempfile.TemporaryDirectory() as root,patch('check_steps.ROOT',Path(root)),patch('check_steps.stages',return_value=[('failed',[sys.executable,'-c','print("FAIL details"); raise SystemExit(3)']),('never',[sys.executable,'-c','print("should not run")'])]):
            self.assertEqual(check_steps.run('release'),1);path=next(Path(root).glob('.local/test-reports/*/report.json'));data=json.loads(path.read_text())
            self.assertEqual(data['status'],'failed');self.assertEqual(len(data['steps']),1);self.assertEqual(data['steps'][0]['exitCode'],3)
            self.assertIn('FAIL details',(path.parent/'failed.log').read_text());self.assertFalse((path.parent/'never.log').exists())

if __name__=='__main__':unittest.main()
