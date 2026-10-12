import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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

def test_checkout_move_preserves_settings_and_rebuilds_env(tmp_path):
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
