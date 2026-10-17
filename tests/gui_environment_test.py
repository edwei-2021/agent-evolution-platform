"""Real launcher-to-provider credential inheritance, with synthetic env files only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
KEY = 'fixture-only $ literal key'


class GuiEnvironmentTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.local')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / '.venv/bin').mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/start-gui.sh', self.root / 'scripts/start-gui.sh')
        self.python = self.root / '.venv/bin/python'
        # The launcher execs this real Python process, which calls the actual
        # provider's freeze/header consumer without importing an SDK or networking.
        probe = f'''#!{sys.executable}
import hashlib,json,os,sys
sys.path.insert(0,{str(ROOT / 'scripts')!r})
from model_provider import freeze,headers
config={{'provider':'strata','apiKeyEnv':'OPENAI_API_KEY'}}
frozen=freeze(config)
print(json.dumps({{
 'probe':True,
 'keyMatches':frozen['apiKeyDigest']=={hashlib.sha256(KEY.encode()).hexdigest()!r},
 'headerMatches':headers(frozen)['Authorization']=='Bearer '+{KEY!r},
 'baseUrlMatches':os.environ.get('OPENAI_BASE_URL')=='http://fixture.invalid:8081/v1',
 'modelMatches':os.environ.get('STRATA_MODEL')=='fixture-model',
 'bothProxyVars':os.environ.get('NO_PROXY')==os.environ.get('no_proxy')=='fixture.invalid,localhost',
 'argv':sys.argv[1:],
 'temporaryPath':os.environ.get('TMPDIR'),
}}))
'''
        self.python.write_text(probe)
        self.python.chmod(0o700)
        self.file = self.root / 'private env with spaces.env'

    def write_env(self, exported=True):
        prefix = 'export ' if exported else ''
        values = {'STRATA_BASE_URL': 'http://fixture.invalid:8081/v1', 'STRATA_MODEL': 'fixture-model',
                  'STRATA_API_KEY': KEY, 'OPENAI_BASE_URL': 'http://fixture.invalid:8081/v1',
                  'OPENAI_API_KEY': KEY, 'NO_PROXY': 'fixture.invalid,localhost', 'no_proxy': 'fixture.invalid,localhost'}
        self.file.write_text('# synthetic fixture only\n' + ''.join(f"{prefix}{k}='{v}'\n" for k, v in values.items()))

    def launch(self, override=None, extra=None, traced=False):
        env = dict(os.environ)
        for key in ('OPENAI_API_KEY', 'STRATA_API_KEY', 'OPENAI_BASE_URL', 'STRATA_BASE_URL', 'STRATA_MODEL',
                    'AEP_STRATA_ENV_FILE', 'BASH_ENV', 'SHELLOPTS', 'BASHOPTS'):
            env.pop(key, None)
        if override is not None:
            env['AEP_STRATA_ENV_FILE'] = str(override)
        env.update(extra or {})
        command = ['bash', *(['-x'] if traced else []), str(self.root / 'scripts/start-gui.sh'), '--port', '8766']
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=5)
        self.assertNotIn(KEY, result.stdout + result.stderr)
        return result

    def result(self, completed):
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(next(line for line in completed.stdout.splitlines() if line.startswith('{')))

    def test_existing_export_file_reaches_actual_provider_freeze_and_headers_without_requests(self):
        self.write_env()
        result = self.launch(self.file)
        data = self.result(result)
        self.assertTrue(all(data[k] for k in ('keyMatches', 'headerMatches', 'baseUrlMatches', 'modelMatches', 'bothProxyVars')))
        self.assertEqual(data['argv'], [str(self.root / 'scripts/serve_gui.py'), '--port', '8766'])
        self.assertEqual(data['temporaryPath'], str(self.root / '.local/tmp'))
        self.assertIn('Strata environment loaded:', result.stdout)

    def test_unexported_assignments_are_exported_and_file_values_override_inherited_values(self):
        self.write_env(exported=False)
        data = self.result(self.launch(self.file, {'OPENAI_API_KEY': 'wrong-inherited-fixture'}))
        self.assertTrue(data['keyMatches'])
        self.assertTrue(data['baseUrlMatches'])

    def test_explicit_empty_override_uses_inherited_key_without_loading_file(self):
        self.write_env()
        result = self.launch('', {'OPENAI_API_KEY': KEY})
        self.assertTrue(self.result(result)['keyMatches'])
        self.assertNotIn('Strata environment loaded', result.stdout)

    def test_explicit_missing_file_stops_before_gui_instead_of_silently_falling_back(self):
        result = self.launch(self.root / 'missing.env', {'OPENAI_API_KEY': KEY})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing or unreadable', result.stderr)
        self.assertNotIn('"probe"', result.stdout)

    def test_failed_or_malformed_source_stops_without_printing_secret_or_starting_gui(self):
        for content in (f"export OPENAI_API_KEY='{KEY}'\nreturn 1\n",
                        f"export OPENAI_API_KEY='{KEY}\n"):
            with self.subTest(content='return failure' if 'return' in content else 'syntax failure'):
                self.file.write_text(content)
                result = self.launch(self.file)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Unable to load', result.stderr)
                self.assertNotIn('"probe"', result.stdout)

    def test_shell_tracing_and_env_file_output_cannot_print_key(self):
        self.write_env()
        with self.file.open('a') as stream:
            stream.write('echo "$OPENAI_API_KEY"\necho "$OPENAI_API_KEY" >&2\n')
        data = self.result(self.launch(self.file, traced=True))
        self.assertTrue(data['keyMatches'])


if __name__ == '__main__':
    unittest.main()
