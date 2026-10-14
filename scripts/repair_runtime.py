"""Local SDK environment discovery; no model requests or user config reads."""
from pathlib import Path
import sys

if __package__:
    from .sdk_runtime_probe import package_status
else:
    from sdk_runtime_probe import package_status

SDK_VERSION = '0.3.5'


def inspect_runtime(root, installed_marker):
    candidate = Path(root) / '.venv-nanobot/bin/python'
    executable = str(candidate) if candidate.is_file() else sys.executable
    return package_status(executable, 'nanobot-ai', 'nanobot', SDK_VERSION, 'Nanobot', installed_marker)


def sdk_status(root):
    path = Path(root) / '.venv-nanobot/bin/python'
    marker = path.stat().st_mtime_ns if path.is_file() else 0
    return inspect_runtime(str(Path(root).resolve()), marker)
