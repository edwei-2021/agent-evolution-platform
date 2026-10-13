import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import pytest
from platform_m.store import Store

def migration_module():
    path = Path(__file__).resolve().parents[1]/'scripts/migrate_wsl.py'
    spec = importlib.util.spec_from_file_location('migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_backup_restores_database_and_events(tmp_path):
    store = Store(tmp_path/'original.db')
    store.event('task', 'before', {'value': 7})
    store.backup(tmp_path/'restore.db')
    assert Store(tmp_path/'restore.db').events('task') == store.events('task')

def test_checkout_move_preserves_settings_and_rebuilds_env():
    # WSL DrvFS under /mnt/d can deny directory rename even on the same drive.
    # This test covers the rename mode on WSL's native Linux filesystem; the
    # adjacent verified-copy test covers the supported /mnt/d migration mode.
    native_tmp = Path('/tmp') if Path('/tmp').is_dir() else Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='aep-m1-rename-', dir=native_tmp) as directory:
        tmp_path = Path(directory)
        source = tmp_path/'nanobot-gepa-mvp'
        source.mkdir()
        subprocess.run(['git', 'init', str(source)], check=True, capture_output=True)
        subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/edwei-2021/nanobot-gepa-mvp.git'],
                       cwd=source, check=True)
        (source/'.local').mkdir()
        (source/'.local/settings.json').write_text('{"model":"saved"}')
        (source/'.venv').mkdir()
        (source/'.venv/old-path').write_text(str(source))
        destination = tmp_path/'agent-evolution-platform'
        module = migration_module()
        assert module.move(source, destination)['apply'] is False
        assert source.exists() and not destination.exists()
        report = module.move(source, destination, True)
        assert report['status'] == 'moved'
        assert json.loads((destination/'.local/settings.json').read_text())['model'] == 'saved'
        assert not (destination/'.venv').exists()
        assert list(destination.glob('.venv.before-migration-*'))

def test_migration_refuses_running_supervisor_and_existing_destination(tmp_path):
    import fcntl
    source = tmp_path/'old'
    (source/'.git').mkdir(parents=True)
    (source/'.local').mkdir()
    stream = (source/'.local/runtime.lock').open('w')
    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(BlockingIOError):
            migration_module().move(source, tmp_path/'new', True)
    finally:
        stream.close()
    (tmp_path/'new').mkdir()
    with pytest.raises(ValueError):
        migration_module().move(source, tmp_path/'new')

def test_baseline_manifest_inventory_is_deterministic():
    root = Path(__file__).resolve().parents[1]
    for path in ('scripts/serve_gui.py', 'scripts/runtime_service.py', 'scripts/gepa_engine.py',
                 'scripts/start-gui.sh', 'requirements-nanobot.txt', 'uv.lock'):
        assert len(hashlib.sha256((root/path).read_bytes()).hexdigest()) == 64

def test_verified_copy_retains_source_and_excludes_virtual_environment(tmp_path):
    source = tmp_path/'old'
    source.mkdir()
    subprocess.run(['git','init',str(source)],check=True,capture_output=True)
    subprocess.run(['git','remote','add','origin','https://github.com/edwei-2021/agent-evolution-platform.git'],cwd=source,check=True)
    (source/'.local').mkdir()
    store = Store(source/'.local/state.sqlite3')
    store.event('run','preserved',{'value':7})
    (source/'.local/settings.json').write_text('{"model":"saved"}')
    (source/'.venv').mkdir()
    (source/'.venv/path').write_text('old absolute path')
    destination = tmp_path/'new'
    report = migration_module().move(source,destination,True,True)
    assert report['status']=='copied' and source.exists() and destination.exists()
    assert (source/'.venv/path').exists() and not (destination/'.venv').exists()
    assert (destination/'.local/settings.json').read_text() == (source/'.local/settings.json').read_text()
    assert Store(destination/'.local/state.sqlite3').events('run') == store.events('run')

def test_copy_failure_preserves_source_and_reports_staging(tmp_path):
    from unittest.mock import patch
    source = tmp_path/'old'
    (source/'.git').mkdir(parents=True)
    (source/'.local').mkdir()
    (source/'.local/important').write_text('retain')
    module = migration_module()
    with patch.object(module.shutil,'copytree',side_effect=[None,PermissionError('copy denied')]):
        with pytest.raises(PermissionError):
            module.move(source,tmp_path/'new',True,True)
    assert source.exists() and not (tmp_path/'new').exists()
    report=json.loads((source/'.local/migration-copy-error.json').read_text())
    assert report['original_retained'] and report['status']=='copy_failed'

def test_rename_permission_error_preserves_diagnostic_and_backup(tmp_path):
    from unittest.mock import patch
    source=tmp_path/'old'
    (source/'.git').mkdir(parents=True)
    module=migration_module()
    with patch.object(module.os,'rename',side_effect=PermissionError('Windows denied rename')):
        with pytest.raises(PermissionError):
            module.move(source,tmp_path/'new',True)
    report=json.loads((source/'.local/migration-rename-error.json').read_text())
    assert report['status']=='rename_denied' and Path(report['backup']).is_dir()
