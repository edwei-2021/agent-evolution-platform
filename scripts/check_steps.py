#!/usr/bin/env python3
"""Fixed staged test profiles with persisted start/end/error evidence."""
import argparse
import ast
from datetime import datetime,timezone
import json
import os
import queue
import re
import signal
import select
import io
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
from native_check_plan import MODULE_CLEANUP_SECONDS

ROOT=Path(__file__).resolve().parents[1]
MONITOR_POLICY = 'overrun-prompt-v1'
MAX_PROMPT_SECONDS = 30 * 60
INTERRUPT_SIGNAL = None
PROGRESS_INTERVAL_SECONDS = 30

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
    if profile=='release' and name in {'native-regressions','monitor-regressions','resume-regressions','frontend-regressions',
                                      'm7-source-scan','m7-unit','m7-ruff','m7-types'}:
        return max(60,historical)
    if profile=='model':return 600
    if profile=='release' and name=='filesystem-calibration':return max(10,historical)
    if profile=='release' and name=='all-frontend':return max(45,historical)
    if profile=='release' and name.split(':',1)[0].split('--',1)[0]=='python-gepa_test':
        from gepa_validation_budget import smoke_budget
        try:
            calibration=calibration or json.loads((reports/'validation-calibration.json').read_text())
            io=float(calibration['perCallIoAllowanceSeconds'])
        except (OSError,ValueError,KeyError,TypeError):
            from adaptive_validation import current
            io=float(current()['perCallIoAllowanceSeconds'])
        if command and '--case' in command:
            from gepa_validation_budget import module_budget
            return module_budget(io, command, ROOT)['normalSeconds']
        full=smoke_budget(io)['workflowSeconds']+30
        # Four cases run complete serial search/final/review workflows. The
        # other eight cases cover datasets, early failures and cancellation.
        # This is a module estimate; each case still prints its own progress.
        return max(historical,4*full+8*60)
    if profile=='release' and name=='python-runtime_test':
        from native_check_plan import build
        plan=build(ROOT)
        return max(historical, 120 + sum(r['normalSeconds'] for r in plan['modules']))
    if profile=='release' and name.startswith('python-'):
        test_file=ROOT/'tests'/(name.removeprefix('python-')+'.py')
        try:
            tree=ast.parse(test_file.read_text())
            count=sum(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')
                      for node in ast.walk(tree))
        except (OSError,SyntaxError):count=1
        # Use measured checkout I/O plus case count on first run; later runs
        # adapt from that module's own successful duration history.
        calibration=0
        try:
            data=json.loads((reports/'validation-calibration.json').read_text())
            calibration=float(data['perCallIoAllowanceSeconds'])
        except (OSError,ValueError,KeyError,TypeError):pass
        per_case=8+min(12,round(calibration*2))
        return max(30,min(900,15+count*per_case),historical)
    return 900

def _wait_answer(buffer):
    """Poll a decision without stopping output draining or deadline checks."""
    if isinstance(sys.stdin, io.StringIO):
        return sys.stdin.readline().strip().lower(), buffer
    try:
        descriptor = sys.stdin.fileno()
        while select.select([descriptor], [], [], 0)[0]:
            character = os.read(descriptor, 1)
            if not character or character == b'\n':
                return buffer.decode(errors='replace').strip().lower(), b''
            buffer += character
            if len(buffer) > 1024:
                return '', b''
    except (OSError, ValueError, AttributeError):
        return '', b''
    return None, buffer


def supervise(process, name, normal, maximum, interval=5, *, output_path=None,
              progress_interval=PROGRESS_INTERVAL_SECONDS, interactive=True, cleanup_seconds=MODULE_CLEANUP_SECONDS):
    started=time.monotonic();prompted=False;approved=False;pending=False;answer_buffer=b''
    events=queue.Queue();reader=None;last_output='';next_progress=started+progress_interval;progress_messages=0
    if process.stdout is not None:
        def collect():
            try:
                for line in process.stdout:events.put(line)
            finally:
                process.stdout.close()
        reader=threading.Thread(target=collect,name='check-step-output',daemon=True);reader.start()
    def drain():
        nonlocal last_output
        while True:
            try:line=events.get_nowait()
            except queue.Empty:break
            last_output=line.rstrip()[-400:]
            if output_path is not None:output_path.write(line);output_path.flush()
            print(line,end='',flush=True)
    def terminate():
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=cleanup_seconds)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait()
    def finish(code, reason=None):
        if reader is not None:reader.join(timeout=1)
        drain()
        elapsed=time.monotonic()-started
        return {'exitCode':code,'durationMs':round(elapsed*1000,3),
                'overNormalSeconds':round(max(0,elapsed-normal),1),
                'extensionApproved':approved,'stoppedByUser':reason in ('user_declined','ctrl_c'),
                'progressMessages':progress_messages,
                **({'stopReason':reason} if reason else {})}
    next_overrun=None
    try:
        while process.poll() is None:
            drain()
            now=time.monotonic()
            elapsed=now-started
            over=round(max(0,elapsed-normal),1)
            # A pending interactive answer must never disable this deadline.
            if elapsed>=maximum:
                print(f'TEST_HARD_LIMIT step={name} over_normal_seconds={over} elapsed_seconds={int(elapsed)} hard_limit_seconds={maximum}; stopping process',flush=True)
                terminate()
                return finish(124,'hard_limit')
            # Both sides are absolute monotonic timestamps; elapsed is a duration.
            if now>=next_progress:
                print(f'TEST_PROGRESS step={name} elapsed_seconds={int(elapsed)} over_normal_seconds={over} '
                      f'last_output={last_output or "waiting_for_test_output"}',flush=True)
                progress_messages+=1
                next_progress=time.monotonic()+progress_interval
            if over and (next_overrun is None or time.monotonic()>=next_overrun):
                print(f'TEST_OVERRUN step={name} over_normal_seconds={over} elapsed_seconds={int(elapsed)} normal_seconds={normal}',flush=True)
                next_overrun=time.monotonic()+interval
            if interactive and elapsed>=prompt_after_seconds(normal) and not prompted:
                prompted=pending=True
                # The newline is required by the parent gate's line forwarder.
                print(f'TEST_WAIT_DECISION step={name} exceeded_normal_seconds={over}. Continue waiting? [y/N]',flush=True)
            if pending:
                answer,answer_buffer=_wait_answer(answer_buffer)
                if answer is not None:
                    pending=False
                    approved=answer in ('y','yes')
                    if not approved:
                        terminate()
                        return finish(125,'user_declined')
                    print(f'TEST_WAIT_APPROVED step={name}; continuing; over_normal_seconds={over}',flush=True)
            try:process.wait(timeout=min(.1,max(.001,maximum-elapsed)))
            except subprocess.TimeoutExpired:pass
    except KeyboardInterrupt:
        terminate()
        return finish(143 if INTERRUPT_SIGNAL == 'SIGTERM' else 130,
                      'sigterm' if INTERRUPT_SIGNAL == 'SIGTERM' else 'ctrl_c')
    return finish(process.returncode)

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
        from check_start_selection import release_plan
        steps=release_plan(root,python,node['path'])
    elif profile!='quick':raise ValueError('Unknown test profile')
    return steps

def run(profile, *, interactive=True, monitor_id=None, plan=None, metadata=None, identifier=None):
    plan=stages(profile) if plan is None else plan
    if not plan:raise ValueError('An empty check plan cannot pass')
    from gepa_validation_budget import expand_plan
    plan=expand_plan(plan, ROOT)
    calibration=None
    if any(name in ('filesystem-calibration','python-canonical_workflow_test') or name.split(':',1)[0].split('--',1)[0]=='python-gepa_test' for name,_ in plan):
        from adaptive_validation import current
        calibration=current()
    # Validate every selected case before dispatching the first model workflow.
    # This also prevents a later excessive calibration from leaving a running
    # report after earlier cases already consumed time.
    from gepa_validation_budget import module_budget, canonical_fixture_budget
    gepa_limits={name:module_budget(calibration['perCallIoAllowanceSeconds'], command, ROOT)
                 for name,command in plan if name.split(':',1)[0].split('--',1)[0]=='python-gepa_test'}
    gepa_limits.update({name:canonical_fixture_budget(calibration['perCallIoAllowanceSeconds'])
                       for name,_ in plan if name=='python-canonical_workflow_test'})
    identifier=identifier or 'CHECK-'+uuid.uuid4().hex
    if not re.fullmatch(r'CHECK-[0-9a-f]{32}',identifier):raise ValueError('Invalid check report identity')
    directory=ROOT/'.local/test-reports'/identifier;directory.mkdir(parents=True)
    logs=DebugLog(ROOT);report={'schemaVersion':1,'id':identifier,'profile':profile,'monitorPolicy':MONITOR_POLICY,'startedAt':datetime.now(timezone.utc).isoformat(),'status':'running','waitPolicy':'interactive' if interactive else 'bounded_non_interactive','steps':[]}
    if metadata is not None:report['scope']=metadata
    def save():
        target=directory/'report.json';temp=directory/'report.tmp';temp.write_text(json.dumps(report,indent=2));temp.replace(target)
    save();print(f'Test report: {directory}',flush=True)
    for index,(name,command) in enumerate(plan,1):
        row={'step':name,'status':'running','startedAt':datetime.now(timezone.utc).isoformat(),'log':name+'.log'};report['steps'].append(row);save()
        step=Step(logs,'runtime','test.'+name,identifier,profile=profile);print(f'STEP_STARTED {name}',flush=True)
        normal=gepa_limits[name]['normalSeconds'] if name in gepa_limits else normal_budget(profile,name,command,calibration=calibration)
        prompt_after=prompt_after_seconds(normal)
        maximum=min(7200,max(normal*20,normal+60,prompt_after+60))
        if name in gepa_limits:
            maximum=gepa_limits[name]['maximumSeconds']
            row['gepaCaseBudget']=gepa_limits[name]
        row.update(normalSeconds=normal,promptAfterSeconds=prompt_after if interactive else None,maximumSeconds=maximum)
        if calibration:
            row['validationCalibration']=calibration
        prompt_text=prompt_after if interactive else 'disabled'
        print(f'STEP_EXPECTED {name} normal_seconds={normal} prompt_after_seconds={prompt_text} hard_limit_seconds={maximum}',flush=True)
        if monitor_id:
            print('CHECK_MONITOR '+json.dumps({'id':monitor_id,'index':index,'step':name,
                  'maximumSeconds':maximum,'report':str(directory/'report.json')}),flush=True)
        try:
            with (directory/row['log']).open('w') as output:
                process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                         text=True,bufsize=1,start_new_session=True,
                                         stdin=None if interactive else subprocess.DEVNULL,
                                         env={**os.environ,'AEP_TEST_REPORT_DIR':str(directory),
                                              **({'AEP_VALIDATION_CALIBRATION':json.dumps(calibration)} if calibration else {})})
                observed=supervise(process,name,normal,maximum,output_path=output,interactive=interactive)
            row['supervisorProgressMessages']=observed.get('progressMessages',0)
            row.update(status='stopped' if observed.get('stopReason')=='user_declined' else
                       'completed' if observed['exitCode']==0 else 'failed',
                       exitCode=observed['exitCode'],durationMs=observed['durationMs'],
                       overNormalSeconds=observed['overNormalSeconds'],extensionApproved=observed['extensionApproved'],stopReason=observed.get('stopReason'))
            if observed.get('stopReason')=='ctrl_c':row['interruptedBy']='Ctrl-C'
            if observed.get('stopReason')=='sigterm':row['interruptedBy']='SIGTERM'
            log_text=(directory/row['log']).read_text(errors='replace')
            row['testCases']=[]
            for line in log_text.splitlines():
                if not line.startswith('TEST_CASE_RESULT '):continue
                try:row['testCases'].append(json.loads(line.removeprefix('TEST_CASE_RESULT ')))
                except ValueError:row['incompleteCaseRecords']=row.get('incompleteCaseRecords',0)+1
            if row['status']=='stopped':row['error']='User chose to stop after the test exceeded ten times its normal duration.'
        except OSError as exc:row.update(status='failed',error=str(exc),exitCode=127,durationMs=0)
        row.update(finishedAt=datetime.now(timezone.utc).isoformat());save()
        step.finish(row['status'],row.get('error') or ('Tests failed; inspect '+row['log'] if row['status']=='failed' else None))
        print(f'STEP_{row["status"].upper()} {name} {row["durationMs"]} ms',flush=True)
        if row['status']!='completed':break
    report.update(status='completed' if all(r['status']=='completed' for r in report['steps']) else 'stopped' if any(r['status']=='stopped' for r in report['steps']) else 'failed',finishedAt=datetime.now(timezone.utc).isoformat());save()
    return int(report['status']!='completed')

if __name__=='__main__':
    def terminate_as_interrupt(signum, frame):
        global INTERRUPT_SIGNAL
        INTERRUPT_SIGNAL = signal.Signals(signum).name
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate_as_interrupt)
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',choices=['quick','model','release'],default='quick')
    parser.add_argument('--non-interactive',action='store_true',help='Run to the frozen step deadlines without stdin prompts')
    parser.add_argument('--monitor-id',help=argparse.SUPPRESS)
    parser.add_argument('--from-step',help='Start at a source-owned release step ID')
    parser.add_argument('--from-case',help='First case in the selected Python release module')
    args=parser.parse_args()
    plan, metadata = None, None
    if args.from_step or args.from_case:
        if args.profile != 'release' or not args.from_step:
            parser.error('--from-case/--from-step require release profile and --from-step')
        from check_start_selection import release_tail
        try:
            plan, omitted = release_tail(stages('release'), ROOT, args.from_step, args.from_case)
        except (ValueError,OSError) as exc:
            parser.error(str(exc))
        metadata = {'kind':'manual-release-start','fullMAcceptance':False,'fullM7Acceptance':False,
                    'startStep':args.from_step,'fromCase':args.from_case,'omittedReleaseSteps':omitted,
                    'priorEvidence':'omitted steps not executed or re-certified'}
        print('RELEASE_SCOPE '+json.dumps(metadata),flush=True)
    raise SystemExit(run(args.profile,interactive=not args.non_interactive,monitor_id=args.monitor_id,
                         plan=plan,metadata=metadata))
