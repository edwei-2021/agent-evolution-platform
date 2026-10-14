"""Slow isolated imports and actionable SDK failures, without model requests."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sdk_runtime_probe as runtime
from repair_runtime import sdk_status
from gepa_runtime import gepa_status
from validation_wait import repair_workflow_seconds


class RuntimeProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = self.root / '.venv-nanobot'
        venv.EnvBuilder(with_pip=False, symlinks=False).create(self.environment)
        self.python = self.environment / 'bin/python'
        self.site = next((self.environment / 'lib').glob('python*/site-packages'))
        runtime._successful_probe.cache_clear()

    def tearDown(self):
        runtime._successful_probe.cache_clear()
        self.temporary.cleanup()

    def package(self, source='class Nanobot: pass\n', version='0.3.5'):
        metadata = self.site / 'nanobot_ai-0.3.5.dist-info'
        metadata.mkdir(exist_ok=True)
        (metadata / 'METADATA').write_text(f'Name: nanobot-ai\nVersion: {version}\n')
        (self.site / 'nanobot.py').write_text(source)

    def inspect(self, **kwargs):
        with redirect_stdout(io.StringIO()) as output:
            result = runtime.probe(self.python, 'nanobot-ai', 'nanobot', '0.3.5', 'Nanobot', **kwargs)
        return result, output.getvalue()

    def test_import_over_old_ten_second_limit_completes_and_reports_progress(self):
        self.package('import time\ntime.sleep(10.2)\nprint("package banner")\nclass Nanobot: pass\n')
        result, output = self.inspect()
        self.assertTrue(result['available'], result)
        self.assertGreater(result['probe']['elapsedSeconds'], 10)
        self.assertIn('SDK_PROBE_WAIT package=nanobot-ai stage=import', output)
        self.assertEqual(result['probe']['modelRequests'], 0)
        self.assertEqual(result['probe']['timeoutSeconds'], 120)

    def test_missing_package_is_distinct_from_import_timeout(self):
        result, _ = self.inspect()
        self.assertFalse(result['available'])
        self.assertEqual(result['errorCode'], 'missing_package')
        self.assertEqual(result['probe']['stage'], 'metadata')

    def test_wrong_version_does_not_import_the_package(self):
        marker = self.root / 'imported'
        self.package(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n', version='9.0.0')
        result, _ = self.inspect()
        self.assertEqual(result['errorCode'], 'version_mismatch')
        self.assertEqual(result['version'], '9.0.0')
        self.assertFalse(marker.exists())

    def test_import_exception_preserves_traceback_and_installed_version(self):
        self.package('raise RuntimeError("fixture import failure")\n')
        result, _ = self.inspect()
        self.assertEqual(result['errorCode'], 'import_error')
        self.assertEqual(result['version'], '0.3.5')
        self.assertIn('fixture import failure', result['probe']['stderr'])

    def test_import_timeout_kills_child_and_retains_partial_stage(self):
        self.package('import time\ntime.sleep(30)\n')
        result, output = self.inspect(seconds=.5, interval=.1)
        self.assertFalse(result['available'])
        self.assertEqual(result['errorCode'], 'probe_timeout')
        self.assertEqual(result['version'], '0.3.5')
        self.assertEqual(result['probe']['stage'], 'import')
        self.assertLess(result['probe']['elapsedSeconds'], 3)
        self.assertIsNotNone(result['probe']['exitCode'])
        self.assertIn('SDK_PROBE_WAIT', output)
        self.assertIn('import time:', result['probe']['stderr'])

    def test_failed_probe_is_not_cached_and_success_cannot_be_mutated(self):
        failed = {'available': False, 'errorCode': 'probe_timeout'}
        success = {'available': True, 'version': '0.3.5'}
        with patch.object(runtime, 'probe', side_effect=[failed, success]) as probe:
            self.assertFalse(runtime.package_status(self.python, 'nanobot-ai', 'nanobot', '0.3.5')['available'])
            result = runtime.package_status(self.python, 'nanobot-ai', 'nanobot', '0.3.5')
            result['available'] = False
            self.assertTrue(runtime.package_status(self.python, 'nanobot-ai', 'nanobot', '0.3.5')['available'])
            self.assertEqual(probe.call_count, 2)

    def test_launch_failure_has_the_interpreter_and_error(self):
        with redirect_stdout(io.StringIO()):
            result = runtime.probe(self.root / 'absent-python', 'nanobot-ai', 'nanobot', '0.3.5')
        self.assertEqual(result['errorCode'], 'launch_error')
        self.assertIn('absent-python', result['error'])

    def test_malformed_output_cannot_pass(self):
        with patch.object(runtime, 'PROGRAM', 'print("unstructured output")'):
            result, _ = self.inspect()
        self.assertEqual(result['errorCode'], 'invalid_output')
        self.assertFalse(result['available'])

    def test_native_process_failure_is_not_reported_as_a_missing_package(self):
        self.package('import os\nos._exit(7)\n')
        result, _ = self.inspect()
        self.assertEqual(result['errorCode'], 'process_error')
        self.assertEqual(result['probe']['exitCode'], 7)
        self.assertEqual(result['probe']['stage'], 'import')

    def test_sdk_uses_project_interpreter_and_gepa_retains_sdk_failure(self):
        self.package()
        with redirect_stdout(io.StringIO()):
            result = sdk_status(self.root)
        self.assertTrue(result['available'], result)
        self.assertEqual(result['python'], str(self.python))
        with patch('gepa_runtime.sdk_status', return_value={'available': False, 'python': str(self.python),
                                                           'errorCode': 'probe_timeout'}):
            gepa = gepa_status(self.root)
        self.assertEqual(gepa['errorCode'], 'sdk_unavailable')
        self.assertEqual(gepa['sdk']['errorCode'], 'probe_timeout')

    def test_repair_budget_covers_wsl_cost_and_rejects_invalid_calibration(self):
        self.assertGreater(repair_workflow_seconds(1.923, 6), 120)
        for value in (float('nan'), float('inf'), -1, 10000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repair_workflow_seconds(value)
        with self.assertRaises(ValueError):
            repair_workflow_seconds(1, True)


if __name__ == '__main__':
    unittest.main()
