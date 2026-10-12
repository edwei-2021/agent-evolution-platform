#!/usr/bin/env python3
"""Fixed staged test profiles with persisted start/end/error evidence."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
from debug_log import DebugLog
from step_trace import Step
from setup_wsl import find_node
from repair_runtime import sdk_status
from gepa_runtime import gepa_status

ROOT=Path(__file__).resolve().parents[1]
def stages(profile,root=ROOT):
    node=find_node(root)
    if not node:raise RuntimeError('Supported Node runtime is required')
    sdk=sdk_status(root);python=sdk['python'] if sdk['available'] else sys.executable
    unit=lambda pattern,*extra:[python,'-m','unittest','discover','-s','tests','-p',pattern,*extra]
    steps=[('trace',unit('step_trace_test.py','-k','StepTests','-v')),
           ('evaluator',unit('step_trace_test.py','-k','BatchTests','-v')),
           ('frontend',[node['path'],'--test',*map(str,sorted((root/'tests').glob('*.test.js')))])]
    if profile=='model':
        if not sdk['available'] or not gepa_status(root)['available']:raise RuntimeError('Install the pinned nanobot/GEPA environment first')
        steps=[('repair-sdk',unit('repair_test.py','-v')),('gepa-sdk',unit('gepa_test.py','-v'))]
    elif profile=='release':
        if not sdk['available'] or not gepa_status(root)['available']:raise RuntimeError('Release checks require real pinned SDKs; skipped SDK tests are not a release pass')
        steps=[('all-frontend',steps[-1][1]),('all-python',unit('*_test.py','-v'))]
    elif profile!='quick':raise ValueError('Unknown test profile')
    return steps

def run(profile):
    plan=stages(profile);identifier='CHECK-'+uuid.uuid4().hex;directory=ROOT/'.local/test-reports'/identifier;directory.mkdir(parents=True)
    logs=DebugLog(ROOT);report={'schemaVersion':1,'id':identifier,'profile':profile,'startedAt':datetime.now(timezone.utc).isoformat(),'status':'running','steps':[]}
    def save():
        target=directory/'report.json';temp=directory/'report.tmp';temp.write_text(json.dumps(report,indent=2));temp.replace(target)
    save();print(f'Test report: {directory}',flush=True)
    for name,command in plan:
        started=time.perf_counter();row={'step':name,'status':'running','startedAt':datetime.now(timezone.utc).isoformat(),'log':name+'.log'};report['steps'].append(row);save()
        step=Step(logs,'runtime','test.'+name,identifier,profile=profile);print(f'STEP_STARTED {name}',flush=True)
        try:
            with (directory/row['log']).open('w') as output:
                result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=900)
            row.update(status='completed' if result.returncode==0 else 'failed',exitCode=result.returncode)
        except (OSError,subprocess.TimeoutExpired) as exc:row.update(status='failed',error=str(exc))
        row.update(finishedAt=datetime.now(timezone.utc).isoformat(),durationMs=round((time.perf_counter()-started)*1000,3));save()
        step.finish(row['status'],row.get('error') or ('Tests failed; inspect '+row['log'] if row['status']=='failed' else None))
        print(f'STEP_{row["status"].upper()} {name} {row["durationMs"]} ms',flush=True)
        if row['status']=='failed':break
    report.update(status='completed' if all(r['status']=='completed' for r in report['steps']) else 'failed',finishedAt=datetime.now(timezone.utc).isoformat());save()
    return int(report['status']!='completed')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['quick','model','release'],default='quick');args=parser.parse_args();raise SystemExit(run(args.profile))
