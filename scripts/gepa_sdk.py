"""Actual pinned GEPA optimizer with serial fresh nanobot evaluations."""
from step_trace import traced
import asyncio
import importlib.metadata
import json
import time
import threading
from gepa import optimize
from gepa.core.adapter import EvaluationBatch
from repair_engine import RepairRunner, verify as verify_repair, TaskCallLimitReached
from repair_sdk import run_sdk
from gepa_engine import progress, child_config, score, training_trace, REFLECTION_SYSTEM
from gepa_dataset import data_for, skill
from gepa_runtime import GEPA_VERSION
from skill_engine import write
from debug_log import DebugLog
from skill_audit import Generation, save, stamp
from gepa_exploration import (exploring, adaptive, proposal_context, CoverageSampler, NovelNonRegression,
                              STRATEGIES, summary, duplicate_of, duplicate_streak, reflection_temperature)

class GlobalRunner(RepairRunner):
    def __init__(self,directory,config,session,tags):
        super().__init__(directory,config);self.session=session;self.tags=tags;self.offset=len(session.calls)
    def call(self,messages,tools):
        if len(self.session.calls)>=self.session.cfg['callBudget']:raise RuntimeError('Global model call budget exhausted')
        return super().call(messages,tools)
    def publish(self,**changes):
        data=super().publish(**changes)
        with self.session.publish_lock:
            # A late callback from a preceding rollout cannot erase a later
            # runner's call suffix or replace its active-call projection.
            if self.offset+len(self.calls)<len(self.session.calls):return data
            tail=[{**c,**self.tags,'id':self.offset+i+1,'localId':c['id']} for i,c in enumerate(self.calls)]
            self.session.calls[self.offset:]=tail
            write(self.session.directory/'gepa-calls.json',self.session.calls)
            summary={k:v for k,v in tail[-1].items() if k not in ('request','response','streamEvents')} if tail else None
            progress(self.session.directory,calls=len(self.session.calls),completedCalls=sum(c['status']=='completed' for c in self.session.calls),
              failedCalls=sum(c['status']=='failed' for c in self.session.calls),lastCall=summary)
        return data

class Session:
    def __init__(self,directory,cfg):
        self.directory=directory;self.cfg=cfg;self.publish_lock=threading.RLock()
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
        with self.publish_lock:
            progress(self.directory,activeRollout=identifier,activeTask=task['id'],phase=stage)
        runner=GlobalRunner(child,cfg,self,{'rolloutId':identifier,'taskId':task['id'],'stage':stage})
        try:
            asyncio.run(run_sdk(child,cfg,runner))
        except TaskCallLimitReached:
            # Only a frozen bank task's verifiable local call cap can continue.
            # Transport, global deadlines and corrupt evidence still propagate.
            pass
        result=verify_repair(child,cfg);write(child/'repair-evaluation.json',result)
        if 'taskOutcome' in result:row.update({k:result[k] for k in ('taskOutcome','sdkStopReason')})
        row.update(score=score(result),evidenceHash=result['evidenceHash'],finishedAt=time.time());self.ledger.append(row)
        write(self.directory/'gepa-rollouts.json',self.ledger)
        with self.publish_lock:
            progress(self.directory,rollouts=len(self.ledger),metricEvaluations=sum(r['stage']=='search' for r in self.ledger))
        print(f'{identifier} {stage} {task["id"]}: trusted task success {row["score"]}',flush=True)
        return row,training_trace(child,row,task)

class Adapter:
    def __init__(self,session):self.session=session;self.search_tasks={t['id']:t for split,rows in data_for(session.cfg).items() if split!='heldout' for t in rows}
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
        train_ids={t['id'] for t in data_for(self.session.cfg)['train']}
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
        train_ids={t['id'] for t in data_for(session.cfg)['train']}
        training=list(reflective_dataset['skill_body'])
        if any(t['taskId'] not in train_ids for t in training):raise ValueError('Final/validation data cannot enter reflection')
        identifier=f'P{len(session.proposals)+1:03d}';child=session.directory/'reflections'/identifier;child.mkdir(parents=True)
        temperature=reflection_temperature(session.cfg,session.proposals)
        cfg={**session.cfg,'callBudget':1,'reflectionOnly':True,'reflectionTemperature':temperature};runner=GlobalRunner(child,cfg,session,{'proposalId':identifier,'stage':'reflection'})
        content=json.dumps(proposal_context(candidate,training,session.proposals,session.cfg),ensure_ascii=False)
        with Generation(session.directory,identifier,session.cfg,skill(candidate['skill_body']),training,
                        'gepa-worker',seed=session.cfg.get('searchSeed',0),skipPerfectScore=not exploring(session.cfg),
                        searchMode=session.cfg.get('searchMode','standard'),strategy=STRATEGIES[len(session.proposals)%len(STRATEGIES)][0] if exploring(session.cfg) else 'training-reflection',
                        acceptance='novel-non-regression' if exploring(session.cfg) else 'strict-improvement',
                        cacheEvaluation=False,useMerge=False,reflectionInstruction=REFLECTION_SYSTEM,metricEvaluations=sum(r['stage']=='search' for r in session.ledger),
                        callsUsed=len(session.calls),temperature=temperature) as audit:
            reply=runner.call([{'role':'system','content':REFLECTION_SYSTEM},{'role':'user','content':content}],[])
            value=json.loads(reply['choices'][0]['message']['content'])
            audit.capture(value.get('skill_body') if isinstance(value,dict) else None)
            if not isinstance(value,dict) or set(value)!={'skill_body'}:raise ValueError('Reflection must return only skill_body JSON')
            body=skill(value['skill_body'])['body']
            audit.generated(skill(body))
            row={'id':identifier,'parentBody':candidate['skill_body'],'candidate':dict(candidate),'training':training,
              'components':components_to_update,'system':REFLECTION_SYSTEM,'input':content,'body':body,'createdAt':time.time()}
            duplicate=duplicate_of(body,session.proposals,session.cfg['baseline']['skill']['body']) if adaptive(session.cfg) else None
            if duplicate is not None:
                row.update(duplicateOf=duplicate,skippedEvaluations=len(training))
                session.search_audit['decisions'].append({'proposalId':identifier,'accepted':False,
                    'reason':'duplicate-before-evaluation','duplicateOf':duplicate,'skippedEvaluations':len(training)})
                save(session.directory/'gepa-search-audit.json',session.search_audit)
            session.proposals.append(row)
            write(session.directory/'gepa-proposals.json',session.proposals);progress(session.directory,proposals=len(session.proposals))
            # Native GEPA's empty-update branch does not evaluate a child. The
            # real model response remains an archived attempt, never a score.
            return {} if duplicate is not None else {'skill_body':body}

@traced('gepa','search')
def search(directory,cfg):
    if importlib.metadata.version('gepa')!=GEPA_VERSION:raise RuntimeError('Unexpected GEPA SDK version')
    logs=DebugLog(cfg['logRoot']);logs.append('gepa','INFO','Real GEPA search started',directory.name,{'metricBudget':cfg['metricBudget'],'profile':cfg['profile']})
    session=Session(directory,cfg);adapter=Adapter(session);data=data_for(cfg);minibatch=cfg['reflectionBatch']
    explore=exploring(cfg);seed=cfg.get('searchSeed',0)
    search_audit={'schemaVersion':1,'seed':seed,'mode':cfg.get('searchMode','standard'),'skipped':[],'decisions':[],'stop':None}
    session.search_audit=search_audit
    class Observer:
        def decision(self,event,accepted):
            if session.proposals:
                search_audit['decisions'].append({'proposalId':session.proposals[-1]['id'],'accepted':accepted,
                    **{k:event[k] for k in ('iteration','new_candidate_idx','old_score','new_score','reason') if k in event}})
                save(directory/'gepa-search-audit.json',search_audit)
        def on_candidate_accepted(self,event):self.decision(event,True)
        def on_candidate_rejected(self,event):self.decision(event,False)
        def on_evaluation_skipped(self,event):
            if len(search_audit['skipped'])<80:
                search_audit['skipped'].append({k:event.get(k) for k in ('iteration','candidate_idx','reason','scores')})
                save(directory/'gepa-search-audit.json',search_audit)
    def stop(state):
        # GEPA stops between iterations; reserve a complete serial iteration
        # (parent + child minibatch + full validation) before it can start.
        used=sum(r['stage']=='search' for r in session.ledger)
        reasons=[]
        if session.fatal is not None:reasons.append('proposal-failed')
        if used+2*minibatch+len(data['validation'])>cfg['metricBudget']:reasons.append('iteration-reservation')
        if len(session.proposals)>=cfg['proposalBudget']:reasons.append('proposal-budget')
        covered={r['taskId'] for r in session.ledger if r['stage']=='search'}
        if adaptive(cfg) and {t['id'] for t in data['train']}<=covered and duplicate_streak(session.proposals,cfg['baseline']['skill']['body'])>=6:reasons.append('duplicate-stagnation')
        if time.time()>=cfg['deadlineEpoch']:reasons.append('deadline')
        if reasons:
            search_audit['stop']={'at':stamp(),'reasons':reasons,'used':used,'metricBudget':cfg['metricBudget'],
                'requiredNext':2*minibatch+len(data['validation']),'proposals':len(session.proposals)}
            save(directory/'gepa-search-audit.json',search_audit)
        return bool(reasons)
    extra={'batch_sampler':CoverageSampler(minibatch,seed),'acceptance_criterion':NovelNonRegression()} if explore else {'reflection_minibatch_size':minibatch}
    result=optimize(seed_candidate={'skill_body':cfg['baseline']['skill']['body']},trainset=data['train'],valset=data['validation'],
      adapter=adapter,callbacks=[Observer()],max_metric_calls=cfg['metricBudget'],stop_callbacks=stop,
      skip_perfect_score=not explore,use_merge=False,cache_evaluation=False,seed=seed,raise_on_exception=True,display_progress_bar=False,**extra)
    if session.fatal is not None:raise RuntimeError('GEPA proposal failed; no retry or final evaluation: '+session.fatal)
    report={'gepaVersion':GEPA_VERSION,'candidates':result.candidates,'validationScores':result.val_aggregate_scores,
      'bestIndex':result.best_idx,'sdkMetricCalls':result.total_metric_calls,'metricCalls':sum(r['stage']=='search' for r in session.ledger),'seed':seed}
    if explore:
        search_audit['exploration']=summary(cfg,session.ledger,session.proposals,result.candidates)
        save(directory/'gepa-search-audit.json',search_audit)
        progress(directory,exploration=search_audit['exploration'])
    write(directory/'gepa-search.json',report)
    selected=skill(result.best_candidate['skill_body']);write(directory/'gepa-selection.json',{'skill':selected,'bestIndex':result.best_idx,'frozenAt':time.time()})
    progress(directory,phase='selection-frozen',selectedSkill=selected,validationScores=report['validationScores'])
    logs.append('gepa','INFO','Validation-selected Skill frozen before final tasks',directory.name,{'bestIndex':result.best_idx,'metricEvaluations':report['metricCalls']})

@traced('gepa','final-evaluation')
def evaluate_final(directory,cfg):
    selected=json.loads((directory/'gepa-selection.json').read_text())['skill'];data=data_for(cfg);session=Session(directory,cfg)
    for split in ('validation','heldout'):
        for label,s in [('baseline',cfg['baseline']['skill']),('selected',selected)]:
            for task in data[split]:session.rollout(task,s['body'],label)
