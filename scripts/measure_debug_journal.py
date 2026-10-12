#!/usr/bin/env python3
"""Measure local journal single vs batch transactions without model requests."""
import argparse
from pathlib import Path
import tempfile
import time
import json
from debug_log import DebugLog

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--records',type=int,default=40)
    args=parser.parse_args()
    if not 1<=args.records<=128:
        parser.error('Use 1..128 records')
    parent=ROOT/'.local/tmp'
    parent.mkdir(parents=True,exist_ok=True)
    results={}
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        for mode in ('single','batch'):
            root=Path(directory)/mode
            journal=DebugLog(root,retention=1000)
            if not journal.available:
                raise SystemExit('Debug journal could not be opened; inspect filesystem permissions')
            journal.keep_open()
            rows=[{'module':'runtime','level':'INFO','message':f'benchmark {i}'} for i in range(args.records)]
            started=time.perf_counter()
            try:
                success=journal.append_many(rows) if mode=='batch' else all(journal.append(**row) for row in rows)
            finally:
                journal.close()
            elapsed=time.perf_counter()-started
            page=DebugLog(root).list(limit=500)
            if not success or page['retained']!=args.records:
                raise SystemExit('Journal count/integrity check failed')
            results[mode]={'seconds':round(elapsed,6),'records':page['retained'],
                           'transactions':1 if mode=='batch' else args.records}
    print(json.dumps({'filesystem_root':str(parent),'results':results,
        'note':'Both cases use the current journal policy and include final close/checkpoint. No model-speed claim.'},indent=2))
