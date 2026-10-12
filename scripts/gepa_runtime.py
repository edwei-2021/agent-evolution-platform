"""Optional GEPA package discovery in the pinned nanobot environment."""
from functools import lru_cache
import json
import subprocess
from repair_runtime import sdk_status

GEPA_VERSION='0.1.4'
@lru_cache(maxsize=8)
def inspect_gepa(python,sdk_available):
    if not sdk_available:return {'available':False,'version':None,'requiredVersion':GEPA_VERSION,'error':'Install SDK and GEPA: bash scripts/install-nanobot.sh'}
    try:
        result=subprocess.run([python,'-I','-c','import gepa,importlib.metadata,json; print(json.dumps({"version":importlib.metadata.version("gepa")}))'],capture_output=True,text=True,timeout=10)
        version=json.loads(result.stdout)['version'] if result.returncode==0 else None
        return {'available':version==GEPA_VERSION,'version':version,'requiredVersion':GEPA_VERSION,'error':None if version==GEPA_VERSION else 'Install pinned GEPA: bash scripts/install-nanobot.sh'}
    except (OSError,ValueError,subprocess.TimeoutExpired):return {'available':False,'version':None,'requiredVersion':GEPA_VERSION,'error':'GEPA environment inspection failed'}

def gepa_status(root):
    sdk=sdk_status(root);return inspect_gepa(sdk['python'],sdk['available'])
