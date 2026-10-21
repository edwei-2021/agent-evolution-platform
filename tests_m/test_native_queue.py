"""Authenticated real native queue plus fail-closed admission and owned cleanup."""
from contextlib import ExitStack
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import zipfile
import pytest
from fastapi.testclient import TestClient
from platform_m.api import create_app
from platform_m.worker import once, native_once
from platform_m.process import execute
from scripts.repair_engine import trusted_test_batch
from scripts.repair_feedback import training_feedback
from scripts.branch_diagnostics import diagnosed
from scripts.export_diagnostics import build_bundle

ROOT=Path(__file__).resolve().parents[1]
HEADERS={'Authorization':'Bearer native-queue-unit','Idempotency-Key':'native-one'}


def test_real_native_submission_freeze_dedup_worker_evaluation_and_readonly_export(tmp_path):
    spec=importlib.util.spec_from_file_location('native_queue_model',ROOT/'tests/repair_test.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.Model;model.calls=[];model.mode='good';model.gate=None;model.entered=threading.Event()
    server=ThreadingHTTPServer(('127.0.0.1',0),model)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    from scripts.ollama_bridge import OllamaBridge,DEFAULTS
    OllamaBridge(tmp_path).save({**DEFAULTS,'host':'127.0.0.1','port':server.server_port,
        'model':'native-loopback','maxTokens':1024,'inferenceTimeout':10},0)
    app=create_app(tmp_path,'native-queue-unit')
    body={'task_id':'PY-clamp-3','skill_body':'Read source, repair, test and summarize.',
          'label':'candidate','repetition':0,'calls':6,'seconds':60,'experiment':'native-proof'}
    def native_tests(jobs,image,timeout=10):
        results=trusted_test_batch(jobs)
        return {'verdict':'pass' if all(r['passed']==r['total'] for r in results) else 'fail',
                'failure_category':'none','results':results,'cleanup':{'removed':True}}
    try:
        with ExitStack() as stack:
            # CI runs the real immutable Docker evaluator. Local component mode
            # uses the actual isolated Python evaluator, labeled separately.
            docker=os.environ.get('M_REQUIRE_DOCKER')=='1'
            if not docker:
                from scripts.run_m_repair import prepare as real_prepare
                def component_prepare(*args,**kwargs):
                    store,artifacts,config,request=real_prepare(*args,**kwargs)
                    return store,artifacts,{**config,'evaluatorImage':None},request
                stack.enter_context(patch('scripts.run_m_repair.prepare',side_effect=component_prepare))
                stack.enter_context(patch('scripts.run_m_repair.image_id',return_value='sha256:'+'a'*64))
                stack.enter_context(patch('platform_m.evaluator.evaluate',side_effect=native_tests))
                stack.enter_context(patch('scripts.run_m_repair.evaluate',side_effect=native_tests))
            with TestClient(app) as client:
                first=client.post('/api/m/nanobot/jobs',json=body,headers=HEADERS)
                assert first.status_code==202,first.text
                identifier=first.json()['id'];store=app.state.store
                before=len(model.calls)
                assert before==0
                with patch('scripts.run_m_repair.prepare',side_effect=AssertionError('Duplicate must not freeze again')):
                    assert client.post('/api/m/nanobot/jobs',json=body,headers=HEADERS).json()['id']==identifier
                assert client.post('/api/m/nanobot/jobs',json={**body,'calls':7},headers=HEADERS).status_code==400
                assert once(store,app.state.artifacts)
                result=client.get('/api/m/jobs/'+identifier,headers=HEADERS).json()
                assert result['state']=='completed',result
                assert result['result']['execution']['status']=='succeeded'
                assert result['result']['evaluation']['verdict']=='pass'
                assert len(model.calls)==4
                assert not once(store,app.state.artifacts)
                events=client.get('/api/m/jobs/'+identifier+'/events',headers=HEADERS)
                assert events.status_code==200 and 'configuration.frozen' in events.text
                with patch('scripts.run_m_repair.prepare',side_effect=AssertionError('Read must not freeze')):
                    assert client.get('/api/m/jobs/'+identifier,headers=HEADERS).status_code==200
                    bundle=build_bundle(tmp_path)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    exported='\n'.join(archive.read(n).decode('utf-8','replace') for n in archive.namelist())
                    assert 'branch.decision' in exported
                    assert 'native.process-cleanup' in exported
                    assert body['skill_body'] not in exported
                    assert module.GOOD not in exported
                    assert 'native-queue-unit' not in exported
                assert len(model.calls)==4
                print('M_NATIVE_QUEUE_RESULT',json.dumps({'requests':4,'dockerEvaluator':docker,'evaluations':1}),flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_native_admission_requires_auth_shape_and_server_owned_image(tmp_path):
    with TestClient(create_app(tmp_path,'native-queue-unit')) as client:
        assert client.post('/api/m/nanobot/jobs',json={}).status_code==401
        for body in ({},{'image':'attacker-image'},['not-an-object']):
            with patch('scripts.run_m_repair.prepare',side_effect=AssertionError('No dispatch')):
                assert client.post('/api/m/nanobot/jobs',json=body,headers=HEADERS).status_code==400


def test_native_lock_and_source_mismatch_never_dispatch_model(tmp_path):
    app=create_app(tmp_path,'native-queue-unit');store=app.state.store;artifacts=app.state.artifacts
    identifier=store.submit('configured',{'environment':{'adapter':'nanobot'}})
    with pytest.raises(ValueError,match='frozen'):
        store.claim_id(identifier,'premature')
    store.configure(identifier,artifacts.put({'provenance':{},'canonicalSourceHash':'invalid'}))
    with (tmp_path/'.local/runtime.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert not native_once(store,artifacts)
        assert store.get(identifier)['state']=='queued'
    with patch('scripts.run_m_repair.execute_frozen',side_effect=AssertionError('No native work')):
        assert native_once(store,artifacts)
    assert store.get(identifier)['state']=='failed'
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM results').fetchone()[0]==0


@pytest.mark.parametrize('stop',['cancelled','timed_out','heartbeat-error'])
def test_owned_native_process_cleanup_preserves_logs_and_original_stop(tmp_path,stop):
    directory=tmp_path/'one'/'two'/'three'/'MRUN-proof';directory.mkdir(parents=True)
    child_pid=directory/'descendant.pid'
    program=("import subprocess,sys,time,pathlib; "
             "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
             "pathlib.Path(sys.argv[1]).write_text(str(p.pid));print('native started',flush=True);time.sleep(60)")
    def cancelled():return stop=='cancelled' and child_pid.exists()
    calls=[]
    def heartbeat():
        calls.append(1)
        if stop=='heartbeat-error':raise RuntimeError('lease-original-failure')
    if stop=='heartbeat-error':
        with pytest.raises(RuntimeError,match='lease-original-failure'):
            execute([sys.executable,'-c',program,str(child_pid)],directory,1,time.time()+1,heartbeat=heartbeat)
        assert not child_pid.exists()
        return
    result=execute([sys.executable,'-c',program,str(child_pid)],directory,1,time.time()+1,
                   cancelled=cancelled,heartbeat=heartbeat)
    assert result['state']==stop
    assert 'native started' in result['stdout']
    pid=int(child_pid.read_text())
    stat=Path(f'/proc/{pid}/stat')
    limit=time.monotonic()+2
    while True:
        try:
            if stat.read_text().split()[2]=='Z':break
        except FileNotFoundError:pass
        try:os.kill(pid,0)
        except ProcessLookupError:break
        assert time.monotonic()<limit,'Owned descendant survived process-group cleanup'
        time.sleep(.01)


def test_feedback_excludes_retained_examples_raw_tools_errors_and_credentials():
    value={'passed':1,'total':2,'records':[{'input':'PROTECTED_INPUT','expected':'PROTECTED_ANSWER'}]}
    feedback,tools=training_feedback({'candidate':{'visible':value,'hidden':value}},[
        {'name':'read_solution','status':'completed','result':'PRIVATE_SOURCE'},
        {'name':'write_solution','status':'failed','error':'secret=PRIVATE_CREDENTIAL'},
        {'name':'run_tests','status':'completed','result':json.dumps(value)}])
    data=json.dumps([feedback,tools])
    for sentinel in ('PROTECTED_INPUT','PROTECTED_ANSWER','PRIVATE_SOURCE','PRIVATE_CREDENTIAL'):
        assert sentinel not in data
    assert feedback['hidden']=={'passed':1,'total':2}
    with pytest.raises(ValueError):training_feedback({'candidate':{'visible':{},'hidden':value}},[])


def test_diagnostic_failure_cannot_replace_business_exception(tmp_path):
    class Work:
        root=tmp_path
        @diagnosed('M3','controlled.failure')
        def fail(self):raise ValueError('original-business-error')
    with patch('diagnostic_log.DiagnosticLog.write',side_effect=OSError('disk failure')) as write:
        with pytest.raises(ValueError,match='original-business-error'):Work().fail()
        assert write.call_count==2


def test_visible_container_failure_latches_original_error_before_another_http_call(tmp_path):
    import repair_engine
    from scripts.m_nanobot_worker import main
    from scripts.repair_fixture import SKILL,BASELINE,PROMPT,VISIBLE,HIDDEN
    directory=tmp_path/'MRUN-infrastructure';directory.mkdir()
    config={'provenance':repair_engine.provenance(),'skill':SKILL,'taskId':'PY-clamp-3',
            'fixture':{'baseline':BASELINE,'prompt':PROMPT,'visible':VISIBLE,'hidden':HIDDEN},
            'evaluatorImage':'sha256:'+'a'*64,'logRoot':str(tmp_path)}
    (directory/'repair-config.json').write_text(json.dumps(config))
    previous=repair_engine.trusted_test
    async def SDK_turn(directory,config,runner):
        with pytest.raises(RuntimeError,match='Container visible evaluation failed'):
            runner.tool('run_tests',{})
        with pytest.raises(RuntimeError,match='Container visible evaluation failed'):
            runner.call([],[])
        raise runner.infrastructure_failure
    invalid={'verdict':'invalid_evaluation','results':[],'cleanup':{'removed':False}}
    with patch('platform_m.evaluator.evaluate',return_value=invalid), \
         patch('scripts.m_nanobot_worker.execute_sdk',side_effect=SDK_turn), \
         patch('repair_engine.stream_chat',side_effect=AssertionError('No further HTTP request')) as transport:
        with pytest.raises(RuntimeError,match='Container visible evaluation failed'):
            main(directory)
        transport.assert_not_called()
    assert repair_engine.trusted_test is previous
    assert not (directory/'canonical-sdk.json').exists()


def test_interrupted_native_external_request_is_not_automatically_replayed(tmp_path):
    app=create_app(tmp_path,'native-queue-unit');store=app.state.store
    identifier=store.submit('interrupted-native',{'environment':{'adapter':'nanobot'}})
    store.configure(identifier,app.state.artifacts.put({'fixed':'configuration'}))
    job=store.claim_id(identifier,'controlled-worker')
    store.transition(identifier,'interrupted',job)
    with pytest.raises(ValueError,match='evidence review'):
        store.resume(identifier,store.get(identifier)['request_hash'])
    assert store.get(identifier)['state']=='interrupted'


@pytest.mark.parametrize('phase',['sdk','hidden-evaluator'])
def test_native_cancel_remains_pending_until_owned_execution_cleanup(tmp_path,phase):
    from platform_m.contracts import RunResult
    from scripts.run_m_repair import execute_frozen
    app=create_app(tmp_path,'native-queue-unit');store=app.state.store;artifacts=app.state.artifacts
    payload={'environment':{'adapter':'nanobot'},'task':{'id':'controlled','split':'search'},
             'release':{'dataset_hash':'d'*64,'evaluator_hash':'e'*64},'label':'baseline','repetition':0}
    identifier=store.submit('cancel-boundary',payload)
    store.configure(identifier,artifacts.put({'frozen':True}))
    job=store.claim_id(identifier,'controlled-cleanup')
    result=RunResult(run_id=identifier,task_id='controlled',status='succeeded',loaded_skill_hash='a'*64,
        environment_snapshot_id='b'*64,release_snapshot_id='c'*64,output={'candidate_source':'pass'})
    entered=threading.Event();release=threading.Event();errors=[]
    def owned_cleanup(*args,**kwargs):
        entered.set()
        if not release.wait(10):raise TimeoutError('Controlled cleanup barrier was not released')
        return result if phase=='sdk' else {'verdict':'pass','results':[{'passed':1,'total':1}],
                                            'cleanup':{'removed':True}}
    def run():
        try:execute_frozen(tmp_path,store,artifacts,job,{'evaluatorImage':'fixed','fixture':{}})
        except BaseException as exc:errors.append(exc)
    with patch('scripts.run_m_repair.NanobotAdapter.run',side_effect=owned_cleanup if phase=='sdk' else None,
               return_value=result),patch('scripts.run_m_repair.evaluate',side_effect=owned_cleanup):
        thread=threading.Thread(target=run);thread.start()
        try:
            assert entered.wait(5)
            with TestClient(app) as client:
                assert client.post('/api/m/jobs/'+identifier+'/cancel',headers=HEADERS).json()['state']=='cancelling'
                pending=client.get('/api/m/jobs/'+identifier,headers=HEADERS).json()
                assert pending['state']=='cancelling' and pending['result'] is None
        finally:release.set();thread.join(timeout=10)
    assert not thread.is_alive() and not errors,errors
    assert store.get(identifier)['state']=='cancelled'
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM results').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0]==0


def test_gui_restart_fences_unfinished_work_without_waiting_for_lease_expiry(tmp_path):
    from types import SimpleNamespace
    from scripts.gepa_canonical import CanonicalGepa
    from platform_m.store import Store
    ledger=Store(tmp_path/'.local/m/control.sqlite3')
    service=SimpleNamespace(root=tmp_path,connect=ledger.db)
    bridge=CanonicalGepa(service)
    config={'canonicalSourceHash':'a'*64,'provenance':{'datasetHash':'b'*64},
            'baseline':{'skill':{'hash':'c'*64}}}
    bridge.prepare('RUN-restart','restart-identity',config)
    identifier=config['canonicalJob']['id'];old=bridge.jobs[identifier]
    run={'id':'RUN-restart','status':'interrupted','gepaConfig':config}
    with ledger.db() as db:
        db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],json.dumps(run)))
    bridge.recover()
    assert ledger.get(identifier)['state']=='interrupted'
    with pytest.raises(RuntimeError,match='Stale worker'):ledger.heartbeat(old)
    with pytest.raises(ValueError,match='evidence review'):ledger.resume(identifier,ledger.get(identifier)['request_hash'])
    assert not native_once(ledger,bridge.artifacts)
