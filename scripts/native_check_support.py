"""Retain runtime/LLM evidence before temporary-workspace cleanup."""
import json
import os
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[1]


def preserve(service, test):
    destination = Path(os.environ.get('AEP_TEST_REPORT_DIR', str(ROOT/'.local/test-reports')))
    module = test.split('.', 1)[0]
    if not module.isidentifier():
        raise ValueError('Invalid test module identity')
    destination = destination/'failure-evidence'/module/(test.rsplit('.', 1)[-1]+'-'+uuid.uuid4().hex)
    destination.mkdir(parents=True)
    run = service.current or {}
    (destination/'diagnostic.json').write_text(json.dumps({'test': test, 'run': run}, indent=2))
    source = service.local/'runs'/str(run.get('id'))
    if source.is_dir():
        for path in sorted(source.iterdir()):
            if path.is_file() and not path.is_symlink() and path.suffix in ('.json', '.log'):
                shutil.copyfile(path, destination/path.name)
    prefix = 'LLM_TEST_SUPPORT ' if module == 'llm_test' else 'NATIVE_TEST_SUPPORT '
    print(prefix + str(destination), flush=True)
    return destination
