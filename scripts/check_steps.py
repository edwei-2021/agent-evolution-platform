#!/usr/bin/env python3
"""Fixed staged test profiles with persisted start/end/error evidence."""
import argparse
import ast
from datetime import datetime,timezone
import json
import os
import queue
import signal
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from debug_log import DebugLog
from step_trace import Step
from setup_wsl import find_node
from repair_runtime import sdk_status
from gepa_runtime import gepa_status

ROOT=Path(__file__).resolve().parents[1]
MONITOR_POLICY = 'overrun-prompt-v1'
MAX_PROMPT_SECONDS = 30 * 60

def prompt_after_seconds(normal):
    return max(normal, min(normal * 10, MAX_PROMPT_SECONDS))

def normal_budget(profile, name, command=None, calibration=None):
    # Use successful measurements only when produced by the same monitor policy.
    reports=ROOT/'.local/test-reports'
    previous=[]
    if reports.is_dir():
        for path in sorted(reports.glob('CHECK-*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:data=json.loads(path.read_text())
            except (OSError,ValueError):continue
            if data.get('profile')!=profile or data.get('monitorPolicy')!=MONITOR_POLICY:continue
            row=next((r for r in data.get('steps',[]) if r.get('step')==name and r.get('status')=='completed'),None)
            if row and isinstance(row.get('durationMs'),(int,float)):previous.append(row['durationMs']/1000)
            if len(previous)>=5:break
    historical=0
    if previous:
        previous.sort()
        historical=round(previous[len(previous)//2]*1.5)
    if profile=='quick' and name not in ('frontend',) and command:
        from adaptive_validation import current
        calibration=current()
        count=0
        for value in command:
            path=Path(value)
            if path.suffix=='.py' and path.is_file():
                try:tree=ast.parse(path.read_text())
                except (OSError,SyntaxError):continue
                count+=sum(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')
                           for node in ast.walk(tree))
        estimate=10+count*calibration['perCallIoAllowanceSeconds']*.5
        return max(15,round(estimate),historical)
    if profile=='quick':return max(45,historical)
    if profile=='model':return 600
    if profile=='release' and name=='all-frontend':return max(45,historical)
    if profile=='release' and name.startswith('python-'):
        test_file=ROOT/'tests'/(name.removeprefix('python-')+'.py')
        try:
            tree=ast.parse(test_file.read_text())
            count=sum(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')
                      for node in ast.walk(tree))
        except (OSError,SyntaxError):count=1
        # First run estimates per module; successful timings then adapt by module.
        return max(30,min(900,15+count*10),historical)
    return 900

def supervise(process, name, normal, maximum, interval=5, *, output_path=None, progress_interval=30):
    started=time.monotonic();prompted=False;approved=False;declined=False
    events=queue.Queue();reader=None;last_output='';next_progress=started+progress_interval
    if process.stdout is not None:
        def collect():
            try:
                for line in process.stdout:events.put(line)
            finally:
                process.stdout.close()
                events.put(None)
        reader=threading.Thread(target=collect,name='check-step-output',daemon=True);reader.start()
    def drain():
        nonlocal last_output
        while True:
            try:line=events.get_nowait()
            except queue.Empty:break
            if line is None:continue
            last_output=line.rstrip()[-400:]
            if output_path is not None:output_path.write(line);output_path.flush()
            print(line,end='',flush=True)
    next_overrun=None
    while process.poll() is None:
        drain()
        elapsed=time.monotonic()-started
        over=round(max(0,elapsed-normal),1)
        if elapsed>=next_progress:
            print(f'TEST_PROGRESS step={name} elapsed_seconds={int(elapsed)} over_normal_seconds={over} '
                  f'last_output={last_output or "waiting_for_test_output"}',flush=True)
            next_progress=time.monotonic()+progress_interval
        if over and (next_overrun is None or time.monotonic()>=next_overrun):
            print(f'TEST_OVERRUN step={name} over_normal_seconds={over} elapsed_seconds={int(elapsed)} normal_seconds={normal}',flush=True)
            next_overrun=time.monotonic()+interval
        if elapsed>=prompt_after_seconds(normal) and not prompted:
            prompted=True
            print(f'TEST_WAIT_DECISION step={name} exceeded_normal_seconds={over}. Continue waiting? [y/N] ',end='',flush=True)
            try:answer=sys.stdin.readline().strip().lower()
            except (EOFError,OSError):answer=''
            approved=answer in ('y','yes')
            declined=not approved
            if declined:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait()
                return {'exitCode':125,'durationMs':round((time.monotonic()-started)*1000,3),
                        'overNormalSeconds':round(max(0,time.monotonic()-started-normal),1),
                        'extensionApproved':False,'stoppedByUser':True,'stopReason':'user_declined'}
            print(f'TEST_WAIT_APPROVED step={name}; continuing; over_normal_seconds={over}',flush=True)
        if elapsed>=maximum:
            print(f'TEST_HARD_LIMIT step={name} over_normal_seconds={over} elapsed_seconds={int(elapsed)} hard_limit_seconds={maximum}; stopping process',flush=True)
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
            return {'exitCode':124,'durationMs':round((time.monotonic()-started)*1000,3),
                    'overNormalSeconds':round(max(0,time.monotonic()-started-normal),1),
                    'extensionApproved':approved,'stoppedByUser':False}
        try:process.wait(timeout=min(.2,maximum-elapsed))
        except subprocess.TimeoutExpired:pass
        except KeyboardInterrupt:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
            elapsed=time.monotonic()-started
            return {'exitCode':130,'durationMs':round(elapsed*1000,3),
                    'overNormalSeconds':round(max(0,elapsed-normal),1),
                    'extensionApproved':approved,'stoppedByUser':True,'stopReason':'ctrl_c'}
    drain()
    if reader is not None:reader.join(timeout=1)
    elapsed=time.monotonic()-started
    return {'exitCode':process.returncode,'durationMs':round(elapsed*1000,3),
            'overNormalSeconds':round(max(0,elapsed-normal),1),'extensionApproved':approved,
            'stoppedByUser':declined}
def stages(profile,root=ROOT):
    node=find_node(root)
    if not node:raise RuntimeError('Supported Node runtime is required')
    sdk=sdk_status(root);python=sdk['python'] if sdk['available'] else sys.executable
    unit=lambda pattern,*extra:[python,'-m','unittest','discover','-s','tests','-p',pattern,*extra]
    steps=[
        ('installer',unit('setup_test.py','-k','InstallerTests','-f','-v')),
        ('setup-control',unit('setup_orchestrator_test.py','-f','-v')),
        ('completion',unit('completion_wait_test.py','-f','-v')),
        ('journal',unit('journal_batch_test.py','-f','-v')),
        ('model-transport',unit('llm_transport_test.py','-f','-v')),
        ('step-trace',unit('step_trace_test.py','-k','StepTests','-f','-v')),
        ('batch-evaluator',unit('step_trace_test.py','-k','BatchTests','-f','-v')),
        ('trace-journal',unit('trace_journal_reuse_test.py','-f','-v')),
        ('frontend',[node['path'],'--test',*map(str,sorted((root/'tests').glob('*.test.js')))])]
    if profile=='model':
        if not sdk['available'] or not gepa_status(root)['available']:raise RuntimeError('Install the pinned nanobot/GEPA environment first')
        steps=[('repair-sdk',unit('repair_test.py','-v')),('gepa-sdk',unit('gepa_test.py','-v'))]
    elif profile=='release':
        if not sdk['available'] or not gepa_status(root)['available']:raise RuntimeError('Release checks require real pinned SDKs; skipped SDK tests are not a release pass')
        steps=[('all-frontend',steps[-1][1])]
        steps.extend(('python-'+path.stem,[python,str(root/'scripts/run_test_module.py'),path.name,
                                           '--tests-dir',str(root/'tests')])
                     for path in sorted((root/'tests').glob('*_test.py')))
    elif profile!='quick':raise ValueError('Unknown test profile')
    return steps

def run(profile):
    plan=stages(profile);identifier='CHECK-'+uuid.uuid4().hex;directory=ROOT/'.local/test-reports'/identifier;directory.mkdir(parents=True)
    logs=DebugLog(ROOT);report={'schemaVersion':1,'id':identifier,'profile':profile,'monitorPolicy':MONITOR_POLICY,'startedAt':datetime.now(timezone.utc).isoformat(),'status':'running','steps':[]}
    def save():
        target=directory/'report.json';temp=directory/'report.tmp';temp.write_text(json.dumps(report,indent=2));temp.replace(target)
    save();print(f'Test report: {directory}',flush=True)
    for name,command in plan:
        started=time.perf_counter();row={'step':name,'status':'running','startedAt':datetime.now(timezone.utc).isoformat(),'log':name+'.log'};report['steps'].append(row);save()
        step=Step(logs,'runtime','test.'+name,identifier,profile=profile);print(f'STEP_STARTED {name}',flush=True)
        normal=normal_budget(profile,name,command)
        prompt_after=prompt_after_seconds(normal)
        maximum=min(7200,max(normal*20,normal+60,prompt_after+60))
        row.update(normalSeconds=normal,promptAfterSeconds=prompt_after,maximumSeconds=maximum)
        print(f'STEP_EXPECTED {name} normal_seconds={normal} prompt_after_seconds={prompt_after} hard_limit_seconds={maximum}',flush=True)
        try:
            with (directory/row['log']).open('w') as output:
                process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                         text=True,bufsize=1,start_new_session=True)
                observed=supervise(process,name,normal,maximum,output_path=output)
            row.update(status='stopped' if observed.get('stopReason')=='user_declined' else
                       'completed' if observed['exitCode']==0 else 'failed',
                       exitCode=observed['exitCode'],durationMs=observed['durationMs'],
                       overNormalSeconds=observed['overNormalSeconds'],extensionApproved=observed['extensionApproved'])
            if observed.get('stopReason')=='ctrl_c':row['interruptedBy']='Ctrl-C'
            log_text=(directory/row['log']).read_text(errors='replace')
            row['testCases']=[json.loads(line.removeprefix('TEST_CASE_RESULT '))
                              for line in log_text.splitlines() if line.startswith('TEST_CASE_RESULT ')]
            if row['status']=='stopped':row['error']='User chose to stop after the test exceeded ten times its normal duration.'
        except OSError as exc:row.update(status='failed',error=str(exc))
        row.update(finishedAt=datetime.now(timezone.utc).isoformat());save()
        step.finish(row['status'],row.get('error') or ('Tests failed; inspect '+row['log'] if row['status']=='failed' else None))
        print(f'STEP_{row["status"].upper()} {name} {row["durationMs"]} ms',flush=True)
        if row['status']!='completed':break
    report.update(status='completed' if all(r['status']=='completed' for r in report['steps']) else 'stopped' if any(r['status']=='stopped' for r in report['steps']) else 'failed',finishedAt=datetime.now(timezone.utc).isoformat());save()
    return int(report['status']!='completed')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['quick','model','release'],default='quick');args=parser.parse_args();raise SystemExit(run(args.profile))
