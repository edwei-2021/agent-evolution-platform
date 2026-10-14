"""Retain native runtime evidence before temporary-workspace cleanup."""
import json
import os
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]


def preserve(service, test):
    destination = Path(os.environ.get('AEP_TEST_REPORT_DIR', str(ROOT/'.local/test-reports')))
    destination = destination/'failure-evidence/runtime_test'/(test.rsplit('.', 1)[-1]+'-'+uuid.uuid4().hex)
    destination.mkdir(parents=True)
    run = service.current or {}
    (destination/'diagnostic.json').write_text(json.dumps({'test': test, 'run': run}, indent=2))
    source = service.local/'runs'/str(run.get('id'))
    if source.is_dir():
        for path in sorted(source.iterdir()):
            if path.is_file() and not path.is_symlink() and path.suffix in ('.json', '.log'):
                shutil.copyfile(path, destination/path.name)
    print('NATIVE_TEST_SUPPORT ' + str(destination), flush=True)
    return destination
