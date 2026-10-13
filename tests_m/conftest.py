from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

import tempfile
import pytest

@pytest.fixture
def posix_tmp_path():
    """Use Linux-native storage for tests that assert POSIX permission bits."""
    native_tmp = Path('/tmp')
    if not native_tmp.is_dir():
        native_tmp = Path(__file__).resolve().parents[1]/'.local/tmp/posix-tests'
        native_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='aep-m6-', dir=native_tmp) as directory:
        yield Path(directory)
