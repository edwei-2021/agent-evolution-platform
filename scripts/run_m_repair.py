#!/usr/bin/env python3
"""Explicit real nanobot execution with container evaluation and canonical evidence."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time
import re
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from platform_m.adapters import NanobotAdapter
from platform_m.contracts import Evaluation
from platform_m.dataset import built_in
from platform_m.evaluator import image_id, evaluate, source_hash
from platform_m.evidence import Artifacts, digest, atomic_write, canonical
from platform_m.store import Store
from branch_diagnostics import diagnosed
from platform_m.gates import source_snapshot
from ollama_bridge import OllamaBridge
from repair_runtime import sdk_status
from repair_fixture import SKILL, TOOLS
from repair_engine import provenance

ROOT = Path(__file__).resolve().parents[1]

@diagnosed('M2','native.configuration')
def prepare(root, task_id, skill_body, label, repetition, image, calls, seconds, experiment):
    if label not in ('baseline','candidate') or type(repetition) is not int or not 0 <= repetition <= 9:
        raise ValueError('Invalid label/repetition')
    if type(calls) is not int or not 2 <= calls <= 12 or type(seconds) is not int or not 60 <= seconds <= 7200:
        raise ValueError('Invalid frozen call/time budget')
    if not isinstance(experiment,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',experiment):
        raise ValueError('Invalid experiment ID')
    root = Path(root)
    store = Store(root/'.local/m/control.sqlite3')
    artifacts = Artifacts(root/'.local/m/artifacts')
    dataset_hash = built_in(artifacts)
    manifest = artifacts.get(dataset_hash)
    task = next((t for t in manifest['tasks'] if t['id'] == task_id), None)
    if task is None:
        raise ValueError('Unknown versioned task ID')
    if not isinstance(skill_body,str) or not skill_body.strip() or len(skill_body.encode()) > 8000:
        raise ValueError('Skill body must be nonempty and <=8 KB')
    image = image_id(image)
    bridge = OllamaBridge(root)
    provider = bridge.frozen()
    if not provider['config']['model']:
        raise ValueError('Save a model in the existing GUI first')
    sdk = sdk_status(ROOT)
    if not sdk['available']:
        raise RuntimeError('Install the pinned nanobot SDK first')
    skill = {**SKILL, 'body': skill_body}
    release = {'skill_hash': artifacts.put(skill), 'workflow_hash': artifacts.put({'workflow':'single-bounded-task-v1'}),
        'runtime_hash': artifacts.put({'adapter':NanobotAdapter.version,'sdk':sdk['version'],'code':provenance(),
                                      'm_source_hash':source_snapshot(ROOT)[0]}),
        'model_policy_hash':artifacts.put({'model':provider['config']['model'],'temperature':0,
            'max_tokens':provider['config']['maxTokens'],'provider_revision':provider['revision'],
            'provider_kind':provider['kind'],'provider_config':provider['config'],'endpoint':provider['endpoint']}),
        'tool_policy_hash':artifacts.put({'tools':list(TOOLS),'scope':'solution.py'}),
        'evaluator_hash':artifacts.put({'image':image,'source_hash':source_hash(ROOT)}),
        'dataset_hash':dataset_hash,'memory_snapshot_hash':artifacts.put({'memory':'empty'}),
        'fixture_hashes':[t['fixture_hash'] for t in manifest['tasks']],
        'budgets':{'calls_per_task':calls,'seconds_per_task':seconds},'result_ids':[], 'parent_release':None}
    # Fair comparison snapshot excludes the evolved Skill and includes fixed runtime/policy/data.
    environment = {k:v for k,v in release.items() if k not in ('skill_hash','result_ids','parent_release')}
    environment['adapter'] = 'nanobot'
    config = {'engine':'nanobot-python-repair-v1','taskId':task_id,'fixture':artifacts.get(task['fixture_hash']),
        'skill':skill,'sdk':sdk,'provider':{**provider,'endpoint':bridge.endpoint(provider['config'])},
        'maxSeconds':seconds,'deadlineEpoch':time.time()+seconds,'callBudget':calls,'callTimeoutSeconds':min(120,seconds),
        'toolBudget':24,'provenance':provenance(),'logRoot':str(root),'evaluatorImage':image,
        'canonicalSourceHash':source_snapshot(ROOT)[0],'sourceRoot':str(ROOT)}
    request = {'task':task,'release':release,'environment':environment,'label':label,'repetition':repetition,
               'experiment':experiment}
    return store, artifacts, config, request


def execute_frozen(root, store, artifacts, job, config):
    identifier=job['id'];request=job['payload'];task=request['task'];release=request['release'];environment=request['environment']
    task_id=task['id'];label=request['label'];repetition=request['repetition']
    dataset_hash=release['dataset_hash'];image=config['evaluatorImage']
    directory = Path(root)/'.local/m/runs'/identifier
    def stopped(result, *, cleanup=True):
        state=store.get(identifier)['state']
        if state not in ('cancelling','cancelled','interrupted'):return False
        store.event(identifier,'execution.stopped',{'status':result.status,'evidence':result.artifacts,
                    'cleanup_confirmed':cleanup})
        if state=='cancelling':store.transition(identifier,'cancelled' if cleanup else 'failed',job)
        return True
    try:
        result = NanobotAdapter().run(task,release,environment,identifier,artifacts,root,directory,config,
            cancelled=lambda:store.get(identifier)['state'] in ('cancelling','cancelled','interrupted'),
            heartbeat=lambda:store.heartbeat(job,90))
        if stopped(result):
            return {'execution':result.model_dump(),'evaluation':None}
        result_ref = artifacts.put(result.model_dump())
        store.checkpoint(job,0,result_ref)
        store.transition(identifier,'evaluating',job)
        if result.status == 'succeeded':
            report = evaluate([{'source':result.output['candidate_source'],'split':'hidden','fixture':config['fixture']}],image)
            if report['verdict'] == 'pass':
                passed = report['results'][0]['passed'] == report['results'][0]['total']
                verdict, category = ('pass','none') if passed else ('fail','assertion')
            else:
                verdict, category = report['verdict'], report['failure_category']
        else:
            verdict = 'fail' if result.status in ('failed','timed_out','cancelled') else 'invalid_evaluation'
            category = 'timeout' if result.status == 'timed_out' else 'infrastructure'
            report = {'execution_status':result.status}
        evidence = artifacts.put(report)
        if stopped(result,cleanup=report.get('cleanup',{}).get('removed',True)):
            return {'execution':result.model_dump(),'evaluation':None}
        e = Evaluation(id=identifier+'-evaluation',run_id=identifier,task_id=task_id,repetition=repetition,label=label,
            split=task['split'],verdict=verdict,evaluator_hash=release['evaluator_hash'],dataset_hash=dataset_hash,
            snapshot_hash=digest(environment),artifacts=[result_ref,evidence],failure_category=category,
            score=None if verdict == 'invalid_evaluation' else int(verdict == 'pass'))
        store.evaluation(e.model_dump())
        final = {'execution':result.model_dump(),'evaluation':e.model_dump(),'release_template':release}
        store.complete(job,final)
        atomic_write(directory/'canonical-evaluation.json',canonical(final))
        return final
    except Exception as exc:
        store.event(identifier,'failed',{'error':str(exc),'debug_code':'DBG-M-004'})
        if store.get(identifier)['state'] in ('running','evaluating','cancelling'):
            store.transition(identifier,'failed',job)
        raise


def run(root, task_id, skill_body, label, repetition, image, calls, seconds, experiment):
    store, artifacts, config, request = prepare(root,task_id,skill_body,label,repetition,image,calls,seconds,experiment)
    identifier = store.submit(digest(request),request)
    old = store.get(identifier)
    if old['state'] == 'completed':
        with store.db() as db:
            return json.loads(db.execute('SELECT data FROM results WHERE job_id=?',(identifier,)).fetchone()[0])
    if old['state'] != 'queued':
        raise RuntimeError('Existing attempt incomplete/failed; inspect evidence before another attempt')
    config=artifacts.get(store.configure(identifier,artifacts.put(config)))
    job = store.claim_id(identifier,'nanobot-cli',seconds=min(max(180,seconds+60),3600))
    if job is None:
        raise RuntimeError('Another worker claimed this task')
    return execute_frozen(root,store,artifacts,job,config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task',default='PY-clamp-1')
    parser.add_argument('--skill-body',type=Path)
    parser.add_argument('--label',choices=['baseline','candidate'],default='baseline')
    parser.add_argument('--repetition',type=int,default=0)
    parser.add_argument('--image',default='aep-evaluator:m')
    parser.add_argument('--calls',type=int,default=6)
    parser.add_argument('--seconds',type=int,default=900)
    parser.add_argument('--experiment',required=True)
    args = parser.parse_args()
    if not 2 <= args.calls <= 12 or not 60 <= args.seconds <= 7200 or not 0 <= args.repetition <= 9:
        parser.error('Invalid time/call/repetition policy')
    lock = ROOT/'.local/runtime.lock'
    lock.parent.mkdir(exist_ok=True)
    stream = lock.open('a+')
    try:
        fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('Stop the legacy GUI before real M task execution; shared model calls must not overlap')
    body = args.skill_body.read_text() if args.skill_body else SKILL['body']
    try:
        result = run(ROOT,args.task,body,args.label,args.repetition,args.image,args.calls,args.seconds,args.experiment)
        print(json.dumps({'run_id':result['execution']['run_id'],'verdict':result['evaluation']['verdict'],
                          'evidence':'.local/m/runs/'+result['execution']['run_id']},indent=2))
    except Exception as exc:
        print('DBG-M-004 real task blocked: '+str(exc)+'; inspect .local/m/runs and canonical events.',file=sys.stderr)
        raise SystemExit(1)
