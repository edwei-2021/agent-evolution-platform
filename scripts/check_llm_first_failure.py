#!/usr/bin/env python3
"""One loopback workflow test, bounded runner and redacted failure support (no Windows requests)."""
import argparse
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
import zipfile

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
    from diagnostic_support import PythonSnapshots, fatal_diagnostics
    original_setup = module.LlmWorkflowTests.setUp
    original_teardown = module.LlmWorkflowTests.tearDown
    def setup(test):
        original_setup(test)
        test.snapshots = PythonSnapshots(directory, capture=lambda: DiagnosticResult.support(None, test))
        test.snapshots.__enter__()
    def teardown(test):
        test.snapshots.__exit__()
        original_teardown(test)
    module.LlmWorkflowTests.setUp = setup
    module.LlmWorkflowTests.tearDown = teardown
    with fatal_diagnostics(directory):
        suite=unittest.TestSuite([module.LlmWorkflowTests('test_actual_worker_reflection_evaluation_review_and_versions')])
        result=unittest.TextTestRunner(verbosity=2,resultclass=DiagnosticResult).run(suite)
        return int(not result.wasSuccessful())

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
        process=subprocess.Popen([sys.executable,'-X','faulthandler',str(Path(__file__).resolve()),'--child',str(directory)],
                                 cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=harness_timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait()
            code=124
    from diagnostic_support import termination
    ended = termination(code)
    crashed = ended['kind'] == 'signal'
    report={'debug_code':'DBG-LLM-CRASH' if crashed else 'DBG-LLM-001','status':'passed' if code==0 else 'failed','exit_code':code,
            'termination':ended,
            'elapsed_seconds':round(time.monotonic()-start,2),'python':sys.executable,
            'wait_policy':'frozen workflow maxSeconds + 10s cleanup; event notification and persisted result',
            'harness_timeout_seconds':harness_timeout,
            'adaptive_calibration':calibration,
            'test':'actual_worker_reflection_evaluation_review_and_versions',
            'remediation':'Inspect fatal.log, environment.json, threads.log, failure-state.json and role log tails. A signal crash is never retried or classified as a timeout.'}
    (directory/'report.json').write_text(json.dumps(report,indent=2))
    if code:
        with zipfile.ZipFile(directory/'support.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in directory.iterdir():
                if path.is_file() and path.suffix in ('.json', '.log'):
                    archive.write(path, path.name)
    print(json.dumps({**report,'support_directory':str(directory),
                     'support_archive':str(directory/'support.zip') if code else None},indent=2))
    print((directory/'test.log').read_text(errors='replace')[-12000:])
    for name in ('fatal.log', 'threads.log'):
        if crashed and (directory/name).exists():
            print(name + ':\n' + (directory/name).read_text(errors='replace')[-12000:])
    raise SystemExit(2 if crashed else code)
