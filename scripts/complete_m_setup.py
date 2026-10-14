#!/usr/bin/env python3
"""One-pass local setup with bounded commands, live progress and retained failure logs."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from statistics import median
from debug_log import redact

ROOT=Path(__file__).resolve().parents[1]
MAX_PROMPT_SECONDS=30*60

def prompt_after_seconds(normal_seconds):
    return max(normal_seconds,min(normal_seconds*10,MAX_PROMPT_SECONDS))

def normal_budget(name,fallback,root=ROOT):
    durations=[]
    reports=Path(root)/'.local/setup-reports'
    if reports.is_dir():
        for path in sorted(reports.glob('SETUP-*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:report=json.loads(path.read_text())
            except (OSError,ValueError):continue
            row=next((r for r in report.get('steps',[]) if r.get('step')==name and r.get('status')=='passed'),None)
            if row:
                start=row.get('started_at');end=row.get('finished_at')
                if isinstance(start,(int,float)) and isinstance(end,(int,float)) and end>=start:
                    durations.append(end-start)
            if len(durations)>=5:break
    return max(10,round(median(durations)*1.5)) if durations else fallback

def safe(text):
    return re.sub(r'https?://[^\s/@]+:[^\s/@]+@','https://[REDACTED]@',redact(text))

def execute(command,root,env,log_path,timeout,normal_seconds=300,label="setup step"):
    prompt_after=prompt_after_seconds(normal_seconds)
    print(f'SETUP_EXPECTED step={label} normal_seconds={normal_seconds} prompt_after_seconds={prompt_after} hard_limit_seconds={timeout}',flush=True)
    process=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,start_new_session=True)
    with log_path.open('w') as log:
        def read():
            for line in process.stdout:
                line=safe(line)
                log.write(line)
                log.flush()
                print(line,end='',flush=True)
        reader=threading.Thread(target=read,daemon=True)
        reader.start()
        started=time.monotonic()
        prompted=False
        approved=False
        try:
            while process.poll() is None:
                elapsed=time.monotonic()-started
                overdue=round(max(0,elapsed-normal_seconds),1)
                if overdue:
                    print(f'SETUP_OVERRUN step={label} over_normal_seconds={overdue} elapsed_seconds={int(elapsed)} normal_seconds={normal_seconds}',flush=True)
                if elapsed>=prompt_after and not prompted:
                    prompted=True
                    print(f'SETUP_WAIT_DECISION step={label} exceeded_normal_seconds={overdue}. Continue waiting? [y/N] ',end='',flush=True)
                    try: answer=sys.stdin.readline().strip().lower()
                    except (EOFError,OSError): answer=''
                    approved=answer in ('y','yes')
                    if not approved:
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid,signal.SIGKILL);process.wait()
                        print(f'SETUP_WAIT_DECLINED step={label}; stopped; over_normal_seconds={overdue}',flush=True)
                        return 125
                    print(f'SETUP_WAIT_APPROVED step={label}; continuing; over_normal_seconds={overdue}',flush=True)
                if elapsed>timeout:
                    print(f'SETUP_HARD_LIMIT step={label} over_normal_seconds={overdue} elapsed_seconds={int(elapsed)} hard_limit_seconds={timeout}; stopping process',flush=True)
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
                    return 124
                print(f'SETUP_PROGRESS step={label} elapsed_seconds={elapsed:.0f} over_normal_seconds={round(max(0,elapsed-normal_seconds),1)} hard_limit_remaining_seconds={max(0,timeout-elapsed):.0f}',flush=True)
                decision_at=normal_seconds*10-elapsed if not prompted else 5
                try:process.wait(timeout=min(5,max(.01,decision_at),max(.01,timeout-elapsed)))
                except subprocess.TimeoutExpired:pass
            return process.returncode
        except KeyboardInterrupt:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()
            return 130
        finally:
            reader.join(timeout=5)
            if not reader.is_alive():
                process.stdout.close()

def main(args):
    directory=ROOT/'.local/setup-reports'/('SETUP-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    report={'status':'running','steps':[],'root':str(ROOT),'model_requests':'loopback fixtures only'}
    def save():
        temp=directory/'report.tmp'
        temp.write_text(json.dumps(report,indent=2))
        temp.replace(directory/'report.json')
    env=os.environ.copy()
    paths=[ROOT/'.tools/uv-env/bin']
    from setup_wsl import find_node
    node=find_node(ROOT)
    if node:paths.append(Path(node['path']).parent)
    env['PATH']=os.pathsep.join(map(str,paths))+os.pathsep+env.get('PATH','')
    temp=ROOT/'.local/tmp'
    temp.mkdir(parents=True,exist_ok=True)
    env.update(TMPDIR=str(temp),TMP=str(temp),TEMP=str(temp),
               TIKTOKEN_CACHE_DIR=str(ROOT/'.local/cache/tiktoken'))
    python=shutil.which(args.python)
    if not python:raise RuntimeError('Requested base Python not found')
    from adaptive_validation import calibrate, ENV
    try:
        calibration = calibrate(ROOT)
    except (OSError, ValueError) as exc:
        report.update(status='blocked', blocked_by='adaptive-calibration',
                      remediation=safe(str(exc)))
        save()
        print(json.dumps(report, indent=2), flush=True)
        print('SUPPORT:', directory / 'report.json', flush=True)
        return 1
    report['adaptive_calibration'] = calibration
    env[ENV] = json.dumps(calibration)
    smoke_seconds = calibration['profiles']['smoke']['maxSeconds']
    full_seconds = calibration['profiles']['full']['maxSeconds']
    print('ADAPTIVE_VALIDATION ' + json.dumps(calibration), flush=True)
    plan=[]
    if (ROOT/'.venv/bin/python').is_file():
        single_normal=max(15,smoke_seconds//10)
        plan.append(('single-llm-gate',[str(ROOT/'.venv/bin/python'),'scripts/check_llm_first_failure.py'],max(smoke_seconds + 65,prompt_after_seconds(single_normal)+60),single_normal))
    base_normal=300
    base_prompt=prompt_after_seconds(base_normal)
    plan.append(('base-environment',['bash','scripts/install-wsl.sh','--python',python],max(1800, full_seconds + 20 * smoke_seconds + 300,base_prompt+60),base_normal))
    plan.append(('nanobot-gepa',['bash','scripts/install-nanobot.sh'],3600,300))
    if not shutil.which('uv',path=env['PATH']):
        plan.extend([('uv-environment',[python,'-m','venv','--copies',str(ROOT/'.tools/uv-env')],720,60),
                     ('uv-install',[str(ROOT/'.tools/uv-env/bin/python'),'-m','pip','install','uv==0.12.23'],1800,120)])
    plan.extend([('m-environment',['bash','scripts/install-m.sh'],3600,300),
                 ('frontend-lock',['npm','ci','--ignore-scripts'],1800,120)])
    if not args.setup_only:
        # Keep the 10x decision point inside the finite acceptance hard cap.
        plan.append(('m-acceptance',[str(ROOT/'.venv-m/bin/python'),'scripts/check_m.py','--profile','acceptance','--non-interactive'],7200,600))
    save()
    print('Setup report:',directory/'report.json',flush=True)
    for name,command,timeout,fallback_normal in plan:
        node=find_node(ROOT)
        if node and str(Path(node['path']).parent) not in env['PATH'].split(os.pathsep):
            env['PATH']=str(Path(node['path']).parent)+os.pathsep+env['PATH']
        normal_seconds=normal_budget(name,fallback_normal)
        timeout=min(7200,max(timeout,prompt_after_seconds(normal_seconds)+60))
        row={'step':name,'status':'running','command':command,'timeout_seconds':timeout,'normal_seconds':normal_seconds,'started_at':time.time()}
        report['steps'].append(row)
        save()
        print('SETUP_STEP_STARTED',name,flush=True)
        try:code=execute(command,ROOT,env,directory/(name+'.log'),timeout,normal_seconds,name)
        except (OSError,ValueError) as exc:
            code=127
            (directory/(name+'.log')).write_text(safe(str(exc)))
        row.update(status='passed' if code==0 else 'stopped' if code in (125,130) else 'failed',exit_code=code,finished_at=time.time())
        row['duration_seconds']=round(row['finished_at']-row['started_at'],3)
        save()
        if code:
            stopped = code in (125,130)
            report.update(status='stopped' if stopped else 'blocked',blocked_by=name,
                stopped_by_user=stopped,
                remediation=('User chose to stop waiting; dependent steps were not started.' if stopped else 'Inspect '+name+'.log and referenced support directory (including fatal.log/environment.json for a native crash). Dependent steps were not started.'))
            save()
            print(json.dumps(report,indent=2),flush=True)
            print('SUPPORT:',directory/'report.json',flush=True)
            return 130 if stopped else 1
    report.update(status='passed',scope='environment only' if args.setup_only else 'declared M machine-check scope')
    save()
    print('SETUP_COMPLETED report='+str(directory/'report.json'),flush=True)
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--python',default='python3.11')
    parser.add_argument('--setup-only',action='store_true')
    args=parser.parse_args()
    raise SystemExit(main(args))
