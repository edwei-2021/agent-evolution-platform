"""Offline installer checks. No package installs or external downloads occur."""
import contextlib
import hashlib
from functools import partial
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import setup_wsl as setup
from serve_gui import GuiHandler


class InstallerTests(unittest.TestCase):
    def test_subprocess_workspace_temp_and_cache_follow_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup.subprocess, 'run') as run:
            project = Path(tmp) / 'project with spaces'
            project.mkdir()
            setup.run(['tool', 'argument'], cwd=project)
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs['cwd'], project.resolve())
            env = kwargs['env']
            for key in ['TMPDIR', 'TMP', 'TEMP']:
                self.assertEqual(env[key], str(project / '.local/tmp'))
            self.assertEqual(env['PIP_CACHE_DIR'], str(project / '.local/cache/pip'))
            self.assertEqual(env['NPM_CONFIG_CACHE'], str(project / '.local/cache/npm'))
            self.assertTrue((project / '.local/tmp').is_dir())

    def test_new_venv_copies_interpreter_into_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, 'run') as run:
            project = Path(tmp)
            setup.create_venv(project)
            self.assertEqual(run.call_args.args[0], [sys.executable, '-m', 'venv', '--copies', '--without-pip', project / '.venv'])
            self.assertEqual(run.call_args.kwargs['cwd'], project)

    def test_wsl2_not_confused_with_wsl1_or_plain_linux(self):
        self.assertTrue(setup.is_wsl2('6.6.87.2-microsoft-standard-WSL2'))
        self.assertFalse(setup.is_wsl2('4.4.0-19041-Microsoft'))
        self.assertFalse(setup.is_wsl2('6.18.44'))

    def test_arch_mapping_and_unsupported_cpu(self):
        self.assertEqual(setup.node_arch('x86_64'), 'x64')
        self.assertEqual(setup.node_arch('aarch64'), 'arm64')
        with self.assertRaises(RuntimeError):
            setup.node_arch('unknown')

    def test_missing_packages_are_selected_without_full_system_upgrade(self):
        def status(argv):
            return 'install ok installed' if argv[-1] != 'curl' else None
        with patch.object(setup, 'capture', side_effect=status), patch.object(setup.shutil, 'which', return_value='/usr/bin/tool'):
            self.assertEqual(setup.missing_packages(), ['curl'])

    def test_apt_installs_only_the_selected_packages(self):
        with patch.object(setup.os, 'geteuid', return_value=0), patch.object(setup, 'run') as run:
            setup.install_apt(['curl', 'xz-utils'])
            self.assertEqual(run.call_args_list[0].args[0], ['apt-get', 'update'])
            self.assertEqual(run.call_args_list[1].args[0], ['apt-get', 'install', '-y', '--no-install-recommends', 'curl', 'xz-utils'])
        with patch.object(setup, 'run') as run:
            setup.install_apt([])
            run.assert_not_called()

    def test_linux_node_only_and_supported_major(self):
        with patch.object(setup, 'capture', return_value='22.23.3|win32'):
            self.assertIsNone(setup.node_info('/fake/node'))
        with patch.object(setup, 'capture', return_value='18.20.0|linux'):
            self.assertFalse(setup.node_info('/fake/node')['supported'])
        with patch.object(setup, 'capture', return_value='24.21.0|linux'):
            self.assertTrue(setup.node_info('/fake/node')['supported'])

    def test_matching_checksum_required_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'node.tar.xz'
            archive.write_bytes(b'fixture')
            sums = Path(tmp) / 'SHASUMS256.txt'
            digest = hashlib.sha256(b'fixture').hexdigest()
            sums.write_text(f'{digest}  node.tar.xz\n')
            self.assertEqual(setup.verify_checksum(archive, sums), digest)
            archive.write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                setup.verify_checksum(archive, sums)
            sums.write_text(f'{digest}  unrelated.tar.xz\n')
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                setup.verify_checksum(archive, sums)
            sums.write_text(f'{digest}  node.tar.xz\n{digest}  node.tar.xz\n')
            with self.assertRaisesRegex(RuntimeError, 'duplicate'):
                setup.verify_checksum(archive, sums)

    def test_failed_download_has_no_partial_published_tool_directory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup.platform, 'machine', return_value='x86_64'), patch.object(setup, 'run', side_effect=subprocess.CalledProcessError(22, 'curl')):
            root = Path(tmp)
            with self.assertRaises(subprocess.CalledProcessError):
                setup.install_node(root)
            self.assertEqual(list((root / '.tools').iterdir()), [])

    def test_installed_venv_is_never_recreated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, 'run') as run:
            root = Path(tmp)
            (root / '.venv').mkdir()
            setup.create_venv(root)
            run.assert_not_called()

    def test_wrong_venv_python_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, 'capture', return_value='3.9'):
            root = Path(tmp)
            (root / '.venv').mkdir()
            report = setup.check_environment(root, allow_non_wsl=True)
            self.assertFalse(report['venv_ready'])
            self.assertTrue(any('Existing .venv' in e for e in report['errors']))

    def test_missing_venv_module_selects_configured_versioned_package(self):
        with patch.object(setup.importlib.util, 'find_spec', return_value=None), patch.object(setup, 'missing_packages', return_value=[]), patch.object(setup, 'capture', return_value='Candidate: 3.11.17-1'):
            report = setup.check_environment(allow_non_wsl=True)
            self.assertIn(f'python{sys.version_info.major}.{sys.version_info.minor}-venv', report['missing_apt_packages'])

    def test_missing_venv_module_without_apt_candidate_is_actionable_error(self):
        with patch.object(setup.importlib.util, 'find_spec', return_value=None), patch.object(setup, 'capture', return_value='Candidate: (none)'):
            report = setup.check_environment(allow_non_wsl=True)
            self.assertTrue(any('no configured APT candidate' in e for e in report['errors']))

    def test_check_only_performs_no_install_or_write(self):
        report = {'ready': False, 'errors': ['fixture']}
        with patch.object(setup, 'check_environment', return_value=report), patch.object(setup, 'install_apt') as apt, patch.object(setup, 'install_node') as node, patch.object(setup, 'create_venv') as venv, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(setup.main(['--check', '--json']), 1)
            self.assertEqual(json.loads(out.getvalue()), report)
            apt.assert_not_called()
            node.assert_not_called()
            venv.assert_not_called()


    def test_installer_uses_quick_release_gated_checks(self):
        with patch.object(setup, 'find_node', return_value={'path': 'node'}), \
             patch.object(setup, 'run') as run:
            setup.run_tests(Path('/project'))
        self.assertEqual(run.call_count, 1)
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:], ['scripts/check_steps.py', '--profile', 'quick'])


class GuiServerTests(unittest.TestCase):
    def test_serves_assets_but_not_checkout_secrets_or_external_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / 'dist'
            dist.mkdir()
            (dist / 'index.html').write_text('<h1>GUI fixture</h1>')
            (dist / 'app.js').write_text('export const demo = true;')
            (root / 'config.env').write_text('private-fixture')
            (dist / 'escape.txt').symlink_to(root / 'config.env')
            (dist / 'empty').mkdir()
            class Quiet(GuiHandler):
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(dist)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base + '/') as response:
                    self.assertIn(b'GUI fixture', response.read())
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                with urlopen(base + '/app.js') as response:
                    self.assertEqual(response.status, 200)
                for path in ['/config.env', '/escape.txt', '/empty/', '/../config.env']:
                    with self.assertRaises(HTTPError) as exc:
                        urlopen(base + path)
                    self.assertEqual(exc.exception.code, 404)
                (dist / 'index.html').unlink()
                (dist / 'index.html').symlink_to(root / 'config.env')
                with self.assertRaises(HTTPError) as exc:
                    urlopen(base + '/')
                self.assertEqual(exc.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
