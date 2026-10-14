#!/usr/bin/env python3
"""Missing acceptance dependencies are blocked (exit 78), never silently skipped."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker', action='store_true')
    parser.add_argument('--sdk', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.docker:
            from platform_m.evaluator import image_id
            import os
            print('Immutable evaluator:', image_id(os.environ.get('M_EVALUATOR_IMAGE','aep-evaluator:m')))
            info = subprocess.run(['docker','info'], capture_output=True,text=True,timeout=15)
            if info.returncode:
                raise RuntimeError('Docker daemon unavailable')
        if args.sdk:
            from scripts.repair_runtime import sdk_status
            from scripts.gepa_runtime import gepa_status
            sdk = sdk_status(root)
            gepa = gepa_status(root, sdk=sdk)
            print('SDK_ENVIRONMENT '+json.dumps({'nanobot':sdk, 'gepa':gepa}), flush=True)
            if not sdk['available'] or not gepa['available']:
                raise RuntimeError('Pinned package probe failed; inspect SDK_ENVIRONMENT diagnostics')
        print('Required dependency check passed')
    except Exception as exc:
        print('BLOCKED: '+str(exc), file=sys.stderr)
        raise SystemExit(78)
