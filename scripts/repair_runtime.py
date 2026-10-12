"""Local SDK environment discovery; no model requests or user config reads."""
from functools import lru_cache
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

SDK_VERSION='0.3.5'

@lru_cache(maxsize=8)
def inspect_runtime(root, installed_marker):
    candidate=Path(root)/'.venv-nanobot/bin/python'
    executable=str(candidate) if candidate.is_file() else sys.executable
    if executable==sys.executable:
        try: version=importlib.metadata.version('nanobot-ai')
        except importlib.metadata.PackageNotFoundError:version=None
        if version!=SDK_VERSION:return {'available':False,'version':version,'requiredVersion':SDK_VERSION,'python':executable,'error':'Install the pinned SDK: bash scripts/install-nanobot.sh'}
    try:
        result=subprocess.run([executable,'-I','-c','from nanobot import Nanobot; import importlib.metadata,json; print(json.dumps({"version":importlib.metadata.version("nanobot-ai")}))'],capture_output=True,text=True,timeout=10)
        version=json.loads(result.stdout)['version'] if result.returncode==0 else None
        return {'available':version==SDK_VERSION,'version':version,'requiredVersion':SDK_VERSION,'python':executable,'error':None if version==SDK_VERSION else 'Pinned nanobot SDK import failed; rerun its installer'}
    except (OSError,ValueError,subprocess.TimeoutExpired):return {'available':False,'version':None,'requiredVersion':SDK_VERSION,'python':executable,'error':'Pinned SDK environment could not be inspected'}

def sdk_status(root):
    path=Path(root)/'.venv-nanobot/bin/python'
    marker=path.stat().st_mtime_ns if path.is_file() else 0
    return inspect_runtime(str(Path(root).resolve()),marker)
