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
import threading
import time
import uuid
from debug_log import redact

ROOT=Path(__file__).resolve().parents[1]

def safe(text):
    return re.sub(r'https?://[^\s/@]+:[^\s/@]+@','https://[REDACTED]@',redact(text))

def execute(command,root,env,log_path,timeout):
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
        try:
            while process.poll() is None:
                elapsed=time.monotonic()-started
                if elapsed>timeout:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
                    return 124
                print(f'SETUP_WAIT elapsed={elapsed:.0f}s remaining={max(0,timeout-elapsed):.0f}s',flush=True)
                try:process.wait(timeout=min(5,max(.01,timeout-elapsed)))
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
        plan.append(('single-llm-gate',[str(ROOT/'.venv/bin/python'),'scripts/check_llm_first_failure.py'],smoke_seconds + 65))
    plan.append(('base-environment',['bash','scripts/install-wsl.sh','--python',python],max(1800, full_seconds + 20 * smoke_seconds + 300)))
    plan.append(('nanobot-gepa',['bash','scripts/install-nanobot.sh'],1200))
    if not shutil.which('uv',path=env['PATH']):
        plan.extend([('uv-environment',[python,'-m','venv','--copies',str(ROOT/'.tools/uv-env')],120),
                     ('uv-install',[str(ROOT/'.tools/uv-env/bin/python'),'-m','pip','install','uv==0.12.23'],600)])
    plan.extend([('m-environment',['bash','scripts/install-m.sh'],1200),
                 ('frontend-lock',['npm','ci','--ignore-scripts'],600)])
    if not args.setup_only:
        plan.append(('m-acceptance',[str(ROOT/'.venv-m/bin/python'),'scripts/check_m.py','--profile','acceptance'],3600))
    save()
    print('Setup report:',directory/'report.json',flush=True)
    for name,command,timeout in plan:
        node=find_node(ROOT)
        if node and str(Path(node['path']).parent) not in env['PATH'].split(os.pathsep):
            env['PATH']=str(Path(node['path']).parent)+os.pathsep+env['PATH']
        row={'step':name,'status':'running','command':command,'timeout_seconds':timeout,'started_at':time.time()}
        report['steps'].append(row)
        save()
        print('SETUP_STEP_STARTED',name,flush=True)
        try:code=execute(command,ROOT,env,directory/(name+'.log'),timeout)
        except (OSError,ValueError) as exc:
            code=127
            (directory/(name+'.log')).write_text(safe(str(exc)))
        row.update(status='passed' if code==0 else 'failed',exit_code=code,finished_at=time.time())
        save()
        if code:
            report.update(status='blocked',blocked_by=name,
                remediation='Inspect '+name+'.log and referenced support directory (including fatal.log/environment.json for a native crash). Dependent steps were not started.')
            save()
            print(json.dumps(report,indent=2),flush=True)
            print('SUPPORT:',directory/'report.json',flush=True)
            return 1
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
