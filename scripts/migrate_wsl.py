#!/usr/bin/env python3
"""Reversible checkout relocation with stopped-service checks and verified state backup."""
import argparse
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and not any(part in ('tmp', 'cache') for part in p.relative_to(root).parts)}

def move(source, destination, apply=False, copy=False):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if source.is_symlink() or destination.is_symlink() or destination.exists() or destination.is_relative_to(source):
        raise ValueError('Destination must be absent, outside source, with no checkout symlink')
    if not (source/'.git').is_dir():
        raise ValueError('Source must be a Git checkout')
    if not copy and source.stat().st_dev != destination.parent.stat().st_dev:
        raise ValueError('Move must stay on the same filesystem; use a reviewed copy migration otherwise')
    plan = {'source': str(source), 'destination': str(destination), 'apply': apply,
            'mode': 'verified-copy' if copy else 'rename',
            'preserves': '.local settings/runs/versions; .tools; Git history',
            'rebuild': ['.venv', '.venv-nanobot', '.venv-m'],
            'remote': 'https://github.com/edwei-2021/agent-evolution-platform.git'}
    if not apply:
        return plan
    local = source/'.local'
    local.mkdir(exist_ok=True)
    handles = []
    try:
        for lock in (local/'runtime.lock', local/'m/service.lock', local/'m/worker.lock'):
            lock.parent.mkdir(parents=True, exist_ok=True)
            stream = lock.open('a+')
            handles.append(stream)
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = source/'.migration-backups'/('before-'+str(time.time_ns()))
        backup.mkdir(parents=True)
        if local.exists():
            if any(p.is_symlink() for p in local.rglob('*')):
                raise ValueError('Review .local symlinks before migration')
            shutil.copytree(local, backup/'local', ignore=shutil.ignore_patterns('tmp','cache'))
            for database in (backup/'local').rglob('*.sqlite3'):
                with closing(sqlite3.connect(database)) as db:
                    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Database backup integrity failure')
        before = files(local)
        (backup/'manifest.json').write_text(json.dumps(before, indent=2))
        if copy:
            staging = Path(tempfile.mkdtemp(prefix='.aep-migration-', dir=destination.parent))
            def ignore(directory, names):
                if Path(directory) == source:
                    return [name for name in names if name.startswith('.venv') or name in
                            ('.migration-backups','node_modules','.pytest_cache','.ruff_cache','.mypy_cache')]
                if Path(directory) == local:
                    return [name for name in names if name in ('tmp','cache')]
                return []
            try:
                shutil.copytree(source, staging, dirs_exist_ok=True, symlinks=True, ignore=ignore)
                if files(staging/'.local') != before:
                    raise ValueError('Copied state hashes differ; original source retained')
                for database in (staging/'.local').rglob('*.sqlite3'):
                    with closing(sqlite3.connect(database)) as db:
                        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise ValueError('Copied database integrity failure')
                result = subprocess.run(['git','remote','set-url','origin',plan['remote']],cwd=staging,
                                        capture_output=True,text=True,timeout=20)
                if result.returncode:
                    raise RuntimeError('Copied Git origin update failed')
                os.rename(staging,destination)
            except BaseException as exc:
                report = {**plan,'status':'copy_failed','staging':str(staging),'error':str(exc),
                          'original_retained':True,'backup':str(backup)}
                (local/'migration-copy-error.json').write_text(json.dumps(report,indent=2))
                raise
            report = {**plan,'status':'copied','original_retained':True,'backup':str(backup),
                      'state_hashes':before,'next':'Use destination; rebuild .venv/.venv-nanobot/.venv-m and run acceptance. Do not run both checkouts.'}
            (destination/'.local/migration-report.json').write_text(json.dumps(report,indent=2))
            return report
        try:
            os.rename(source, destination)
        except PermissionError:
            (local/'migration-rename-error.json').write_text(json.dumps({**plan,'status':'rename_denied',
                'backup':str(backup),'original_retained':True,
                'remediation':'Close Windows editors/terminals using the checkout, or rerun --copy --apply to retain the original and verify a new checkout.'},indent=2))
            raise
        try:
            if files(destination/'.local') != before:
                raise ValueError('State hashes differ after move')
            result = subprocess.run(['git', 'remote', 'set-url', 'origin', plan['remote']], cwd=destination,
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Git origin update failed')
            for env in plan['rebuild']:
                if (destination/env).exists():
                    os.rename(destination/env, destination/(env+'.before-migration-'+str(time.time_ns())))
            report = {**plan, 'status': 'moved', 'backup': str(destination/backup.relative_to(source)),
                      'state_hashes': before, 'next': 'bash scripts/install-wsl.sh; bash scripts/install-nanobot.sh; bash scripts/install-m.sh'}
            (destination/'.local/migration-report.json').write_text(json.dumps(report, indent=2))
            return report
        except BaseException:
            os.rename(destination, source)
            raise
    finally:
        for handle in handles:
            handle.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=Path('/mnt/d/agent-evolution-platform'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--copy', action='store_true', help='Verified copy retaining source; bypass source directory rename on Windows drives')
    args = parser.parse_args()
    try:
        print(json.dumps(move(ROOT, args.destination, args.apply, args.copy), indent=2))
    except Exception as exc:
        print('DBG-M-001 migration blocked: '+str(exc)+'; stop GUI/API/worker, inspect paths and backup.', file=sys.stderr)
        raise SystemExit(1)
