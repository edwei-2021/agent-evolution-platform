"""Owned process-group supervision with absolute bounds and retained private logs."""
import os
import signal
import subprocess
import time
from scripts.branch_diagnostics import record


def execute(command, directory, seconds, deadline, *, cancelled=None, heartbeat=None):
    cancelled=cancelled or (lambda:False)
    heartbeat=heartbeat or (lambda:None)
    root=directory.parents[3]
    limit=time.monotonic()+max(0,min(seconds,deadline-time.time()))
    state='succeeded';code=None;child=None
    out_path=directory/'sdk.stdout.log';err_path=directory/'sdk.stderr.log'
    try:
        heartbeat()
        if cancelled():state='cancelled'
        elif time.monotonic()>=limit:state='timed_out'
        else:
            with out_path.open('x') as output,err_path.open('x') as error:
                child=subprocess.Popen(command,stdout=output,stderr=error,stdin=subprocess.DEVNULL,start_new_session=True)
                record(root,'M2','native.process','started',identifier=directory.name,pid=child.pid,limitSeconds=seconds)
                next_heartbeat=time.monotonic()+20
                while child.poll() is None:
                    if out_path.stat().st_size+err_path.stat().st_size>16*1024*1024:
                        raise RuntimeError('Native SDK log limit exceeded; no further work allowed')
                    if cancelled():state='cancelled';break
                    if time.monotonic()>=limit:state='timed_out';break
                    if time.monotonic()>=next_heartbeat:
                        heartbeat();next_heartbeat=time.monotonic()+20
                    time.sleep(.05)
                if state=='succeeded':code=child.wait(timeout=1)
    finally:
        if child is not None:
            # Kill the owned group even if its direct parent has already exited.
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait(timeout=5)
            code=child.returncode
        record(root,'M2','native.process-cleanup',state,identifier=directory.name,
               dispatched=child is not None,exitCode=code,processStopped=child is None or child.poll() is not None)
    def tail(path,size):
        if not path.exists():return ''
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-size));return stream.read(size).decode('utf-8','replace')
    return {'state':state,'exit_code':code,'stdout':tail(out_path,4000),'stderr':tail(err_path,8000)}
