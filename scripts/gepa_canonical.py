"""Canonical ledger bridge for explicitly enabled GUI GEPA supervision."""
import copy
import json
import hashlib
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from platform_m.contracts import Evaluation, Experiment, RunResult, Usage
from platform_m.evidence import Artifacts, digest
from platform_m.store import Store
from platform_m.gates import source_snapshot
from branch_diagnostics import diagnosed, record
from gepa_dataset import data_for, skill


class CanonicalGepa:
    def __init__(self,service):
        self.service=service;self.root=service.root
        self.store=Store(self.root/'.local/m/control.sqlite3')
        self.artifacts=Artifacts(self.root/'.local/m/artifacts')
        self.jobs={};self.markers={};self.heartbeats={}

    @diagnosed('M3','gepa.canonical.freeze')
    def prepare(self,run_id,request_id,config):
        if not config.get('canonicalSourceHash'):config['canonicalSourceHash']=source_snapshot(ROOT)[0]
        frozen=self.artifacts.put(config)
        identifier=self.store.submit('gui-gepa:'+request_id,{
            'run_id':run_id,'config_hash':frozen,'environment':{'adapter':'gepa'},
            'dataset_hash':config['provenance']['datasetHash'],'skill_hash':config['baseline']['skill']['hash']})
        job=self.store.claim_id(identifier,'gui-gepa-supervisor',90)
        if job is None:raise RuntimeError('Canonical GEPA job is already owned; no model request dispatched')
        self.store.checkpoint(job,0,frozen)
        self.jobs[identifier]=job;self.heartbeats[identifier]=time.monotonic()
        config['canonicalJob']={'id':identifier,'configHash':frozen}

    def observe(self,run):
        meta=run.get('gepaConfig',{}).get('canonicalJob')
        if not meta:return
        identifier=meta['id'];job=self.jobs[identifier]
        if time.monotonic()-self.heartbeats[identifier]>=20:
            self.store.heartbeat(job,90);self.heartbeats[identifier]=time.monotonic()
        marker=(run['status'],tuple((a['role'],a['status'],a.get('pid'),a.get('exitCode')) for a in run['agents']))
        if self.markers.get(identifier)!=marker:
            self.store.event(identifier,'gui.lifecycle',{'run_id':run['id'],'state':run['status'],
                'roles':[{'role':a['role'],'state':a['status'],'pid':a.get('pid'),'exit_code':a.get('exitCode')} for a in run['agents']]})
            self.markers[identifier]=marker
            record(self.root,'M3','gepa.canonical.lifecycle',run['status'],identifier=identifier,roles=len(run['agents']))

    def cancel_requested(self,run):
        meta=run.get('gepaConfig',{}).get('canonicalJob')
        return bool(meta and self.store.get(meta['id'])['state'] in ('cancelling','cancelled','interrupted'))

    @diagnosed('M3','gepa.canonical.finalize')
    def finish(self,run):
        meta=run.get('gepaConfig',{}).get('canonicalJob')
        if not meta:return
        job=self.jobs[meta['id']];result=run.get('gepaResult')
        if self.service.ollama.operation.locked():
            raise RuntimeError('Canonical terminal publication requires released provider slot')
        cfg=run['gepaConfig'];frozen=self.artifacts.get(meta['configHash'])
        if {k:v for k,v in cfg.items() if k!='canonicalJob'}!=frozen:
            raise ValueError('Canonical GEPA snapshot changed after dispatch')
        self.store.heartbeat(job,90)
        if self.cancel_requested(run):
            run.update(status='cancelled',checksPassed=False)
            if result:result['checksPassed']=False
            self.store.transition(job['id'],'cancelled',job)
            with self.service.connect() as db:
                db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(run),run['id']))
            return
        if run['status']=='completed':
            if not result or result.get('checksPassed') is not True:
                raise ValueError('Canonical completion requires independent GEPA review')
            experiment=Experiment(id=job['id'],state='completed',
                snapshots={'configuration':meta['configHash'],'dataset':cfg['provenance']['datasetHash']},
                budgets={k:cfg[k] for k in ('metricBudget','proposalBudget','callBudget','maxSeconds')},
                consumed={k:result[k] for k in ('metricEvaluations','proposals','calls','rollouts')}).model_dump()
            saved={'experiment':experiment,'evaluation':result,'legacy_run':copy.deepcopy(run)}
            artifact=self.artifacts.put(saved)
            self.store.checkpoint(job,1,artifact)
            self.store.transition(job['id'],'evaluating',job)
            self.store.complete(job,saved)
        else:
            self.store.transition(job['id'],'cancelled' if run['status']=='cancelled' else 'failed',job)
        record(self.root,'M3','gepa.canonical.terminal',run['status'],identifier=job['id'],
               reviewed=bool(result and result.get('checksPassed')),providerReleased=not self.service.ollama.operation.locked())

    def recover(self):
        """Reconcile view publication only; never resume an external call at startup."""
        with self.service.connect() as db:
            rows=db.execute('SELECT id,data FROM runs').fetchall()
        for run_id,raw in rows:
            run=json.loads(raw);meta=run.get('gepaConfig',{}).get('canonicalJob')
            if not meta:continue
            job=self.store.get(meta['id'])
            if job['state']=='completed':
                with self.store.db() as db:
                    saved=json.loads(db.execute('SELECT data FROM results WHERE job_id=?',(job['id'],)).fetchone()[0])
                original=saved['legacy_run']
                if original['id']!=run_id or original['gepaConfig']!=run['gepaConfig']:
                    raise ValueError('Canonical/GUI recovery identity mismatch')
                if run['status']!=original['status']:
                    with self.service.connect() as db:
                        db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(original),run_id))
            elif job['state'] in ('failed','cancelled','interrupted') and run['status']=='completed':
                run.update(status=job['state'],checksPassed=False)
                with self.service.connect() as db:
                    db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(run),run_id))
            elif job['state'] in ('running','evaluating','cancelling'):
                self.store.interrupt_gui(job['id'],job['fence'],run_id)
                record(self.root,'M3','gepa.canonical.recovery','interrupted',identifier=job['id'])


@diagnosed('M3','gepa.canonical.rollout')
def save_rollout(directory,config,row,evaluation,task):
    meta=config.get('canonicalJob')
    if not meta:return
    root=Path(config['logRoot']);store=Store(root/'.local/m/control.sqlite3')
    artifacts=Artifacts(root/'.local/m/artifacts')
    identifier=meta['id']+'-'+row['id'];split=next(s for s,rows in data_for(config).items() if any(t['id']==task['id'] for t in rows))
    split={'train':'search','validation':'validation','heldout':'independent_test'}[split]
    child=directory/'rollouts'/row['id']
    source=(child/'repair-candidate.py').read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=evaluation['candidateHash']:raise ValueError('Canonical source differs from verified repair')
    execution=RunResult(run_id=identifier,task_id=task['id'],status='failed' if evaluation.get('taskOutcome')=='call-limit' else 'succeeded',
        release_snapshot_id=digest({'configuration':meta['configHash'],'body':row['body']}),
        environment_snapshot_id=meta['configHash'],loaded_skill_hash=skill(row['body'])['hash'],
        artifacts=[artifacts.put({'native_evidence':evaluation['evidenceHash'],'source_hash':evaluation['candidateHash']})],
        output={'candidate_source':source,'canonical_job_id':meta['id'],'rollout_id':row['id'],'stage':row['stage'],'sdk_stop_reason':evaluation.get('sdkStopReason','completed')},
        usage=Usage(tool_calls=evaluation['toolCalls'],wall_time_ms=1000*(row['finishedAt']-row['startedAt']))).model_dump()
    execution_ref=artifacts.put(execution);result_ref=artifacts.put(evaluation)
    value=Evaluation(id=identifier,run_id=identifier,task_id=task['id'],repetition=row.get('repetition',0),
        label='baseline' if row['body']==config['baseline']['skill']['body'] else 'candidate',split=split,
        verdict='pass' if row['score'] else 'fail',score=row['score'],
        evaluator_hash=digest(config['provenance']['repair']),dataset_hash=config['provenance']['datasetHash'],
        snapshot_hash=meta['configHash'],artifacts=[execution_ref,result_ref],
        failure_category='none' if row['score'] else 'timeout' if evaluation.get('taskOutcome')=='call-limit' else 'assertion').model_dump()
    store.evaluation(value)
    store.event(meta['id'],'rollout.committed',{'run_id':config['runId'],'rollout_id':row['id'],
        'task_id':task['id'],'stage':row['stage'],'repetition':row.get('repetition',0),
        'score':row['score'],'execution_hash':execution_ref,
        'evidence_hash':evaluation['evidenceHash'],'tool_count':evaluation['toolCalls'],'model_calls':evaluation['calls']})
