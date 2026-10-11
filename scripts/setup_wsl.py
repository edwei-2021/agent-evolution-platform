#!/usr/bin/env python3
"""Check/install the GUI development environment. No third-party Python imports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from serve_gui import DEFAULT_PORT

ROOT = Path(__file__).resolve().parents[1]
NODE_VERSION = '22.23.3'
APT_PACKAGES = {'git': 'git', 'curl': 'curl', 'ca-certificates': None,
                'xz-utils': 'xz', 'tar': 'tar', 'iproute2': 'ip'}
SUPPORTED_NODE_MAJORS = {22, 24, 26}


def read_os_release(path=Path('/etc/os-release')):
    values = {}
    try:
        for line in path.read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values


def is_wsl2(kernel):
    kernel = kernel.lower()
    return 'microsoft' in kernel and ('wsl2' in kernel or 'microsoft-standard' in kernel)


def node_arch(machine):
    mapping = {'x86_64': 'x64', 'amd64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}
    if machine.lower() not in mapping:
        raise RuntimeError(f'Unsupported Node architecture: {machine}. Supported: x86_64 / aarch64.')
    return mapping[machine.lower()]


def capture(argv):
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def node_info(executable):
    if not executable:
        return None
    text = capture([str(executable), '-p', 'process.versions.node + "|" + process.platform'])
    if not text or not re.fullmatch(r'\d+\.\d+\.\d+\|linux', text):
        return None
    version = text.split('|')[0]
    return {'path': str(Path(executable).resolve()), 'version': version,
            'supported': int(version.split('.')[0]) in SUPPORTED_NODE_MAJORS}


def find_node(root=ROOT):
    try:
        pinned = root / '.tools' / f'node-v{NODE_VERSION}-linux-{node_arch(platform.machine())}' / 'bin/node'
    except RuntimeError:
        pinned = None
    for executable in [pinned, shutil.which('node')]:
        if executable and (info := node_info(executable)) and info['supported']:
            return info
    return None


def missing_packages():
    missing = []
    for package, command in APT_PACKAGES.items():
        status = capture(['dpkg-query', '-W', '-f=${Status}', package])
        if status != 'install ok installed' or command and not shutil.which(command):
            missing.append(package)
    return missing


def check_environment(root=ROOT, allow_non_wsl=False):
    os_info = read_os_release()
    errors = []
    if platform.system() != 'Linux' or os_info.get('ID') != 'ubuntu' or os_info.get('VERSION_ID') != '24.04':
        errors.append('This installer targets Ubuntu 24.04 on Linux.')
    if not is_wsl2(platform.release()) and not allow_non_wsl:
        errors.append('WSL2 kernel not detected. Verify wsl -l -v in Windows PowerShell. Use --allow-non-wsl only for deliberate Ubuntu 24.04 VM/container validation.')
    if sys.version_info < (3, 11):
        errors.append('Python 3.11+ required. Rerun with --python /path/to/python3.11.')
    try:
        arch = node_arch(platform.machine())
    except RuntimeError as exc:
        arch = None
        errors.append(str(exc))
    for module in ['sqlite3', 'fcntl']:
        try:
            importlib.import_module(module)
        except ImportError:
            errors.append(f'Python {module} support is unavailable; repair the selected interpreter through its provider.')
    for name in ['index.html', 'styles.css', 'js/app.js', 'js/adapter.js', 'js/domain.js', 'js/runtime-client.js', 'js/runtime-view.js', 'js/skill-view.js', 'js/ollama-ui.js', 'js/llm-view.js']:
        if not (root / 'dist' / name).is_file():
            errors.append(f'Missing frontend asset: dist/{name}. Use a complete repository checkout.')
    for name in ['serve_gui.py', 'runtime_service.py', 'native_agents.py', 'skill_engine.py', 'skill_agents.py', 'skill_store.py', 'ollama_bridge.py', 'configure_ollama.py', 'test_windows_ollama.py', 'llm_engine.py', 'llm_agents.py', 'llm_store.py']:
        if not (root / 'scripts' / name).is_file():
            errors.append(f'Missing runtime source: scripts/{name}. Use a complete repository checkout.')
    for name in ['SKILL.md', 'dataset.json']:
        if not (root / 'skills/title-normalizer' / name).is_file():
            errors.append(f'Missing skill fixture: skills/title-normalizer/{name}. Use a complete repository checkout.')
    venv_path = root / '.venv' / 'bin/python'
    venv_ready = False
    if (root / '.venv').exists():
        version = capture([str(venv_path), '-c', 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")'])
        if version != f'{sys.version_info.major}.{sys.version_info.minor}':
            errors.append('Existing .venv uses a different or unavailable Python. Move it aside yourself and rerun; it will not be overwritten.')
        else:
            venv_ready = True
    packages = missing_packages()
    venv_module_available = importlib.util.find_spec('venv') is not None
    if not venv_module_available:
        package = f'python{sys.version_info.major}.{sys.version_info.minor}-venv'
        policy = capture(['apt-cache', 'policy', package]) or ''
        candidate = re.search(r'Candidate:\s*(\S+)', policy)
        if candidate and candidate.group(1) != '(none)':
            packages.append(package)
        else:
            errors.append(f'Python venv module is missing and {package} has no configured APT candidate. Repair venv using the provider of this Python installation; no PPA will be added automatically.')
    node = find_node(root)
    return {'schema_version': 1, 'mode': 'gui-native-runtime', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'os': os_info.get('PRETTY_NAME', 'unknown'), 'kernel': platform.release(),
            'wsl2_detected': is_wsl2(platform.release()), 'allow_non_wsl': allow_non_wsl,
            'architecture': arch, 'python': {'path': sys.executable, 'version': platform.python_version()},
            'missing_apt_packages': packages, 'node': node, 'venv_ready': venv_ready,
            'venv_module_available': venv_module_available,
            'errors': errors, 'ready': not errors and not packages and bool(node) and venv_ready}


def print_report(report):
    print('nanobot GEPA MVP — environment check', flush=True)
    print(f"OS: {report['os']} | WSL2: {report['wsl2_detected']} | CPU: {report['architecture']}")
    print(f"Python: {report['python']['version']} ({report['python']['path']})")
    print('Missing APT packages: ' + (', '.join(report['missing_apt_packages']) or 'none'))
    print('Node: ' + (f"{report['node']['version']} ({report['node']['path']})" if report['node'] else 'missing / unsupported / non-Linux'))
    print('Project .venv: ' + ('ready' if report['venv_ready'] else 'not ready'))
    for error in report['errors']:
        print('ERROR: ' + error)
    print('Status: ' + ('READY' if report['ready'] else 'NOT READY'), flush=True)


def run(argv, cwd=ROOT):
    project = Path(cwd).resolve()
    temp = project / '.local' / 'tmp'
    cache = project / '.local' / 'cache'
    temp.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({'TMPDIR': str(temp), 'TMP': str(temp), 'TEMP': str(temp),
                'XDG_CACHE_HOME': str(cache), 'PIP_CACHE_DIR': str(cache / 'pip'),
                'NPM_CONFIG_CACHE': str(cache / 'npm')})
    print('Running: ' + ' '.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=project, env=env, check=True)


def install_apt(packages):
    if not packages:
        return
    if os.geteuid() == 0:
        prefix = []
    else:
        if not shutil.which('sudo'):
            raise RuntimeError('sudo is missing; ask the administrator to install: ' + ' '.join(packages))
        run(['sudo', '-v'])
        prefix = ['sudo']
    run(prefix + ['apt-get', 'update'])
    run(prefix + ['apt-get', 'install', '-y', '--no-install-recommends', *packages])


def verify_checksum(archive, sums):
    expected = None
    for line in sums.read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == archive.name:
            if expected is not None or not re.fullmatch('[0-9a-fA-F]{64}', fields[0]):
                raise RuntimeError('Invalid or duplicate checksum entry.')
            expected = fields[0].lower()
    if expected is None:
        raise RuntimeError(f'Official checksum entry missing for {archive.name}.')
    with archive.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError('Node checksum mismatch; archive will not be extracted.')
    return actual


def install_node(root=ROOT):
    arch = node_arch(platform.machine())
    stem = f'node-v{NODE_VERSION}-linux-{arch}'
    tools = root / '.tools'
    tools.mkdir(exist_ok=True)
    destination = tools / stem
    if destination.exists():
        raise RuntimeError(f'Incomplete or unsupported local Node at {destination}; move it aside before retrying.')
    with tempfile.TemporaryDirectory(prefix='node-download-', dir=tools) as tmp:
        temp = Path(tmp)
        archive = temp / f'{stem}.tar.xz'
        sums = temp / 'SHASUMS256.txt'
        for path in [archive, sums]:
            run(['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https', '--tlsv1.2',
                 '--connect-timeout', '20', '--max-time', '300', '--retry', '2',
                 f'https://nodejs.org/dist/v{NODE_VERSION}/{path.name}', '--output', path])
        digest = verify_checksum(archive, sums)
        run(['tar', '-xJf', archive, '-C', temp, '--no-same-owner'])
        extracted = temp / stem
        info = node_info(extracted / 'bin/node')
        if not info or info['version'] != NODE_VERSION:
            raise RuntimeError('Downloaded Node failed its version check.')
        # Rename only a fully extracted, verified tool directory on the same filesystem.
        extracted.rename(destination)
    return {'version': NODE_VERSION, 'sha256': digest, 'source': 'https://nodejs.org/dist/'}


def create_venv(root=ROOT):
    destination = root / '.venv'
    if not destination.exists():
        try:
            run([sys.executable, '-m', 'venv', '--copies', '--without-pip', destination], cwd=root)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError('Python venv creation failed. Check that your Python distribution provides the venv module. This GUI does not require pip or third-party Python packages. An incomplete .venv is kept for inspection; move it aside before retrying.') from exc


def run_tests(root=ROOT):
    node = find_node(root)
    if not node:
        raise RuntimeError('A supported Linux Node runtime is required for tests.')
    run([node['path'], '--test', *sorted((root / 'tests').glob('*.test.js'))], cwd=root)
    run([root / '.venv/bin/python', '-m', 'unittest', 'discover', '-s', 'tests', '-p', '*_test.py'], cwd=root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only check; no APT, downloads, .venv or report file writes.')
    parser.add_argument('--allow-non-wsl', action='store_true', help='Deliberately test on Ubuntu 24.04 Linux outside WSL2.')
    parser.add_argument('--json', action='store_true', help='Machine-readable output with --check.')
    args = parser.parse_args(argv)
    if args.json and not args.check:
        parser.error('--json requires --check')
    report = check_environment(allow_non_wsl=args.allow_non_wsl)
    if args.check:
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_report(report)
        return 0 if report['ready'] else 1
    print_report(report)
    if report['errors']:
        return 1
    install_apt(report['missing_apt_packages'])
    node_download = None
    if not find_node():
        node_download = install_node()
    create_venv()
    final = check_environment(allow_non_wsl=args.allow_non_wsl)
    print_report(final)
    if not final['ready']:
        raise RuntimeError('Environment is still incomplete; see the check output above.')
    run_tests()
    final['tests_passed'] = True
    final['node_download'] = node_download
    final['git_commit'] = capture(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'])
    target = ROOT / '.local' / 'environment.json'
    target.parent.mkdir(exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(final, indent=2) + '\n')
    os.replace(temp, target)
    print(f'Installation complete. Local report: {target}\nStart: bash scripts/start-gui.sh\nOpen: http://localhost:{DEFAULT_PORT}\nCustom port: bash scripts/start-gui.sh --port <number>')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
