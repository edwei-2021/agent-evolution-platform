#!/usr/bin/env python3
"""One loopback workflow test, bounded runner and redacted failure support (no Windows requests)."""
import argparse
import faulthandler
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]

def child(directory):
    sys.path.insert(0,str(ROOT/'scripts'))
    from debug_log import redact
    spec=importlib.util.spec_from_file_location('first_llm',ROOT/'tests/llm_test.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class DiagnosticResult(unittest.TextTestResult):
        def support(self,test):
            service=getattr(test,'service',None)
            run=getattr(service,'current',None) or {}
            data={'status':run.get('status'),'run_id':run.get('id'),'mock_calls':len(module.MockModel.calls),
                  'roles':[{k:agent.get(k) for k in ('role','status','pid','exitCode','error','updatedAt')}
                           for agent in run.get('agents',[])]}
            if run.get('id') and service:
                source=service.local/'runs'/run['id']
                progress=source/'llm-progress.json'
                if progress.is_file():
                    try:data['progress']=json.loads(progress.read_text())
                    except (OSError,ValueError):pass
                for role in ('coordinator','worker','reflector','evaluator','reviewer'):
                    path=source/(role+'.log')
                    if path.is_file():
                        (directory/(role+'.log')).write_text(redact(path.read_text(errors='replace')[-20000:]))
            (directory/'failure-state.json').write_text(json.dumps(data,indent=2))
        def addFailure(self,test,error):
            self.support(test)
            super().addFailure(test,error)
        def addError(self,test,error):
            self.support(test)
            super().addError(test,error)
    with (directory/'threads.log').open('w') as stream:
        stream.write('Periodic 25-second stack samples; the workflow test uses its frozen budget, not this sampling interval.\n')
        stream.flush()
        faulthandler.dump_traceback_later(25,repeat=True,file=stream)
        try:
            suite=unittest.TestSuite([module.LlmWorkflowTests('test_actual_worker_reflection_evaluation_review_and_versions')])
            result=unittest.TextTestRunner(verbosity=2,resultclass=DiagnosticResult).run(suite)
            return int(not result.wasSuccessful())
        finally:
            faulthandler.cancel_dump_traceback_later()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',type=Path)
    args=parser.parse_args()
    if args.child:
        raise SystemExit(child(args.child))
    directory=ROOT/'.local/test-reports'/('LLM-CHECK-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    from adaptive_validation import current, harness_seconds
    calibration = current()
    os.environ['AEP_VALIDATION_CALIBRATION'] = json.dumps(calibration)
    harness_timeout = harness_seconds()
    start=time.monotonic()
    with (directory/'test.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child',str(directory)],
                                 cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=harness_timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait()
            code=124
    report={'debug_code':'DBG-LLM-001','status':'passed' if code==0 else 'failed','exit_code':code,
            'elapsed_seconds':round(time.monotonic()-start,2),'python':sys.executable,
            'wait_policy':'frozen workflow maxSeconds + 10s cleanup; event notification and persisted result',
            'harness_timeout_seconds':harness_timeout,
            'adaptive_calibration':calibration,
            'test':'actual_worker_reflection_evaluation_review_and_versions',
            'remediation':'Inspect test.log, failure-state.json, threads.log and role log tails; budgets were calibrated before dispatch; inspect the retained evidence.'}
    (directory/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({**report,'support_directory':str(directory)},indent=2))
    print((directory/'test.log').read_text(errors='replace')[-12000:])
    raise SystemExit(code)
