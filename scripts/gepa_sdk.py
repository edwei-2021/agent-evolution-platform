"""Actual pinned GEPA optimizer with serial fresh nanobot evaluations."""
from step_trace import traced
import asyncio
import importlib.metadata
import json
import time
from gepa import optimize
from gepa.core.adapter import EvaluationBatch
from repair_engine import RepairRunner, verify as verify_repair
from repair_sdk import run_sdk
from gepa_engine import progress, child_config, score, training_trace, REFLECTION_SYSTEM
from gepa_dataset import dataset, skill
from gepa_runtime import GEPA_VERSION
from skill_engine import write
from debug_log import DebugLog

class GlobalRunner(RepairRunner):
    def __init__(self,directory,config,session,tags):
        super().__init__(directory,config);self.session=session;self.tags=tags;self.offset=len(session.calls)
    def call(self,messages,tools):
        if len(self.session.calls)>=self.session.cfg['callBudget']:raise RuntimeError('Global model call budget exhausted')
        return super().call(messages,tools)
    def publish(self,**changes):
        data=super().publish(**changes)
        tail=[{**c,**self.tags,'id':self.offset+i+1,'localId':c['id']} for i,c in enumerate(self.calls)]
        self.session.calls[self.offset:]=tail
        write(self.session.directory/'gepa-calls.json',self.session.calls)
        summary={k:v for k,v in tail[-1].items() if k not in ('request','response','streamEvents')} if tail else None
        progress(self.session.directory,calls=len(self.session.calls),completedCalls=sum(c['status']=='completed' for c in self.session.calls),
          failedCalls=sum(c['status']=='failed' for c in self.session.calls),lastCall=summary)
        return data

class Session:
    def __init__(self,directory,cfg):
        self.directory=directory;self.cfg=cfg
        self.ledger=json.loads((directory/'gepa-rollouts.json').read_text())
        self.calls=json.loads((directory/'gepa-calls.json').read_text())
        self.proposals=json.loads((directory/'gepa-proposals.json').read_text());self.fatal=None
    @traced('gepa','rollout')
    def rollout(self,task,body,stage):
        if time.time()>=self.cfg['deadlineEpoch']:raise RuntimeError('GEPA workflow time budget exhausted')
        identifier=f'R{len(self.ledger)+1:04d}';child=self.directory/'rollouts'/identifier;child.mkdir(parents=True)
        cfg=child_config(self.cfg,task,body);write(child/'repair-config.json',cfg)
        workspace=child/'task-workspace';workspace.mkdir()
        (workspace/'solution.py').write_text(task['fixture']['baseline']);(workspace/'AGENTS.md').write_text('Use only the three granted tools on solution.py.\n')
        (child/'repair-baseline.py').write_text(task['fixture']['baseline'])
        write(child/'repair-tools.json',[]);write(child/'repair-calls.json',[])
        write(child/'repair-reflection.json',{'kind':'gepa-evaluation','fixedSkillHash':skill(body)['hash']})
        row={'id':identifier,'stage':stage,'taskId':task['id'],'body':body,'startedAt':time.time()}
        progress(self.directory,activeRollout=identifier,activeTask=task['id'],phase=stage)
        runner=GlobalRunner(child,cfg,self,{'rolloutId':identifier,'taskId':task['id'],'stage':stage})
        asyncio.run(run_sdk(child,cfg,runner))
        result=verify_repair(child,cfg);write(child/'repair-evaluation.json',result)
        row.update(score=score(result),evidenceHash=result['evidenceHash'],finishedAt=time.time());self.ledger.append(row)
        write(self.directory/'gepa-rollouts.json',self.ledger)
        progress(self.directory,rollouts=len(self.ledger),metricEvaluations=sum(r['stage']=='search' for r in self.ledger))
        print(f'{identifier} {stage} {task["id"]}: trusted task success {row["score"]}',flush=True)
        return row,training_trace(child,row,task)

class Adapter:
    def __init__(self,session):self.session=session;self.search_tasks={t['id']:t for split,rows in dataset(session.cfg['profile']).items() if split!='heldout' for t in rows}
    def evaluate(self,batch,candidate,capture_traces=False):
        if set(candidate)!={'skill_body'}:raise ValueError('Only the Skill body may evolve')
        body=skill(candidate['skill_body'])['body']
        used=sum(r['stage']=='search' for r in self.session.ledger)
        if used+len(batch)>self.session.cfg['metricBudget']:raise RuntimeError('Hard metric evaluation budget exhausted')
        outputs=[];traces=[];scores=[]
        for task in batch:
            if self.search_tasks.get(task['id'])!=task:raise ValueError('Search cannot access final tasks')
            row,trace=self.session.rollout(task,body,'search');outputs.append({'rolloutId':row['id'],'score':row['score']});traces.append(trace);scores.append(float(row['score']))
        return EvaluationBatch(outputs=outputs,scores=scores,trajectories=traces if capture_traces else None,num_metric_calls=len(batch))
    def make_reflective_dataset(self,candidate,eval_batch,components_to_update):
        if components_to_update!=['skill_body']:raise ValueError('Unexpected reflected component')
        train_ids={t['id'] for t in dataset(self.session.cfg['profile'])['train']}
        if not eval_batch.trajectories or any(t['taskId'] not in train_ids for t in eval_batch.trajectories):raise ValueError('Only training traces may be reflected')
        return {'skill_body':eval_batch.trajectories}
    def propose_new_texts(self,candidate,reflective_dataset,components_to_update):
        try:return self._propose(candidate,reflective_dataset,components_to_update)
        except Exception as exc:
            # GEPA catches individual proposal errors internally. Latch the
            # failure so its next stop check cannot retry or enter final data.
            self.session.fatal=str(exc);write(self.session.directory/'gepa-failure.json',{'error':str(exc)})
            DebugLog(self.session.cfg['logRoot']).append('gepa','ERROR','Proposal failed: '+str(exc),self.session.directory.name)
            raise
    @traced('gepa','proposal')
    def _propose(self,candidate,reflective_dataset,components_to_update):
        session=self.session
        if components_to_update!=['skill_body'] or set(reflective_dataset)!={'skill_body'}:raise ValueError('Unexpected proposal component')
        if len(session.proposals)>=session.cfg['proposalBudget']:raise RuntimeError('Reflection proposal budget exhausted')
        train_ids={t['id'] for t in dataset(session.cfg['profile'])['train']}
        training=list(reflective_dataset['skill_body'])
        if any(t['taskId'] not in train_ids for t in training):raise ValueError('Final/validation data cannot enter reflection')
        identifier=f'P{len(session.proposals)+1:03d}';child=session.directory/'reflections'/identifier;child.mkdir(parents=True)
        cfg={**session.cfg,'callBudget':1,'reflectionOnly':True};runner=GlobalRunner(child,cfg,session,{'proposalId':identifier,'stage':'reflection'})
        content=json.dumps({'candidate':candidate,'training':training},ensure_ascii=False)
        reply=runner.call([{'role':'system','content':REFLECTION_SYSTEM},{'role':'user','content':content}],[])
        value=json.loads(reply['choices'][0]['message']['content'])
        if not isinstance(value,dict) or set(value)!={'skill_body'}:raise ValueError('Reflection must return only skill_body JSON')
        body=skill(value['skill_body'])['body']
        session.proposals.append({'id':identifier,'parentBody':candidate['skill_body'],'candidate':dict(candidate),'training':training,
          'components':components_to_update,'system':REFLECTION_SYSTEM,'input':content,'body':body,'createdAt':time.time()})
        write(session.directory/'gepa-proposals.json',session.proposals);progress(session.directory,proposals=len(session.proposals))
        return {'skill_body':body}

@traced('gepa','search')
def search(directory,cfg):
    if importlib.metadata.version('gepa')!=GEPA_VERSION:raise RuntimeError('Unexpected GEPA SDK version')
    logs=DebugLog(cfg['logRoot']);logs.append('gepa','INFO','Real GEPA search started',directory.name,{'metricBudget':cfg['metricBudget'],'profile':cfg['profile']})
    session=Session(directory,cfg);adapter=Adapter(session);data=dataset(cfg['profile']);minibatch=cfg['reflectionBatch']
    def stop(state):
        # GEPA stops between iterations; reserve a complete serial iteration
        # (parent + child minibatch + full validation) before it can start.
        used=sum(r['stage']=='search' for r in session.ledger)
        return session.fatal is not None or used+2*minibatch+len(data['validation'])>cfg['metricBudget'] or len(session.proposals)>=cfg['proposalBudget'] or time.time()>=cfg['deadlineEpoch']
    result=optimize(seed_candidate={'skill_body':cfg['baseline']['skill']['body']},trainset=data['train'],valset=data['validation'],
      adapter=adapter,max_metric_calls=cfg['metricBudget'],stop_callbacks=stop,reflection_minibatch_size=minibatch,
      skip_perfect_score=True,use_merge=False,cache_evaluation=False,seed=0,raise_on_exception=True,display_progress_bar=False)
    if session.fatal is not None:raise RuntimeError('GEPA proposal failed; no retry or final evaluation: '+session.fatal)
    report={'gepaVersion':GEPA_VERSION,'candidates':result.candidates,'validationScores':result.val_aggregate_scores,
      'bestIndex':result.best_idx,'sdkMetricCalls':result.total_metric_calls,'metricCalls':sum(r['stage']=='search' for r in session.ledger),'seed':0}
    write(directory/'gepa-search.json',report)
    selected=skill(result.best_candidate['skill_body']);write(directory/'gepa-selection.json',{'skill':selected,'bestIndex':result.best_idx,'frozenAt':time.time()})
    progress(directory,phase='selection-frozen',selectedSkill=selected,validationScores=report['validationScores'])
    logs.append('gepa','INFO','Validation-selected Skill frozen before final tasks',directory.name,{'bestIndex':result.best_idx,'metricEvaluations':report['metricCalls']})

@traced('gepa','final-evaluation')
def evaluate_final(directory,cfg):
    selected=json.loads((directory/'gepa-selection.json').read_text())['skill'];data=dataset(cfg['profile']);session=Session(directory,cfg)
    for split in ('validation','heldout'):
        for label,s in [('baseline',cfg['baseline']['skill']),('selected',selected)]:
            for task in data[split]:session.rollout(task,s['body'],label)
