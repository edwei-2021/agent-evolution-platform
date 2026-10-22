"""Trusted GEPA evidence contracts; imports no optimizer in the GUI process."""
from model_provider import payload as provider_payload
from step_trace import traced
from gepa_exploration import exploring, adaptive, proposal_context, summary, duplicate_of, reflection_temperature, POLICY
import hashlib
import json
from pathlib import Path
from repair_engine import provenance as repair_provenance, verify as verify_repair, ROOT, TASK_FAILURE_POLICY
from repair_fixture import digest
from repair_transport import ToolAccumulator
from gepa_dataset import data_for, dataset_hash, skill, DATASET_VERSION
from gepa_runtime import GEPA_VERSION
from gepa_comparison import POLICY as COMPARISON_POLICY, paired_final, release_blockers
from skill_engine import write
from repair_feedback import POLICY as FEEDBACK_POLICY, training_feedback
from branch_diagnostics import diagnosed, record as decision

ENGINE='gepa-nanobot-repair-v1'
TASKS={'coordinator':'Freeze grouped benchmark and search budgets','worker':'Run real GEPA with fresh nanobot rollouts',
       'reflector':'Freeze the validation-selected Skill','evaluator':'Evaluate frozen baseline/selected Skills on final data','reviewer':'Replay trusted evidence and review release gates'}
REFLECTION_SYSTEM='Improve only the generic Python repair Skill body using the supplied training trajectories. Do not output solution code or modify Skill name/description. Return exactly a JSON object with one string field: skill_body. Use valid JSON escaping for newlines, quotes and backslashes inside the string; no Markdown fences or surrounding commentary. Keep the body concise enough to finish within the output budget. Keep instructions general; do not embed task IDs or test answers.'

def provenance(profile,frozen=None):
    return {'engine':ENGINE,'comparisonPolicy':COMPARISON_POLICY,'feedbackPolicy':FEEDBACK_POLICY,'gepaVersion':GEPA_VERSION,'datasetVersion':frozen['version'] if frozen else DATASET_VERSION,'datasetHash':frozen['hash'] if frozen else dataset_hash(profile),'repair':repair_provenance(),
      'codeHashes':{n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ('gepa_dataset.py','challenge_bank.py','gepa_engine.py','gepa_sdk.py','gepa_agents.py','skill_audit.py','gepa_exploration.py','gepa_comparison.py','repair_feedback.py','gepa_canonical.py')}}

def progress(directory,**changes):
    p=directory/'gepa-progress.json';data=json.loads(p.read_text()) if p.exists() else {'engine':ENGINE,'phase':'queued','calls':0,'completedCalls':0,'failedCalls':0,'metricEvaluations':0,'proposals':0,'rollouts':0,'lastCall':None}
    data.update(changes);write(p,data);return data

def child_config(cfg,task,body):
    return {'engine':'nanobot-python-repair-v1','taskId':task['id'],'skill':skill(body),'fixture':task['fixture'],
      'sdk':cfg['sdk'],'provider':cfg['provider'],'maxSeconds':cfg['maxSeconds'],'deadlineEpoch':cfg['deadlineEpoch'],
      'callBudget':cfg['taskCallBudget'],'callTimeoutSeconds':cfg['callTimeoutSeconds'],'toolBudget':24,
      'provenance':cfg['provenance']['repair'],'logRoot':cfg['logRoot'],'correlationRunId':cfg['runId'],
      **({'taskFailurePolicy':cfg['taskFailurePolicy']} if cfg['profile']=='bank' else {})}

def score(result):
    return int(result['repairPassed'])

@diagnosed('M5','gepa.evidence.verify')
@traced('gepa','evidence.verify')
def verify(directory, progress_callback=None):
    directory=Path(directory);cfg=json.loads((directory/'gepa-config.json').read_text())
    if cfg['provenance']!=provenance(cfg['profile'],cfg.get('datasetSnapshot')):raise ValueError('GEPA code or dataset provenance changed')
    if cfg.get('comparisonPolicy')!=cfg['provenance'].get('comparisonPolicy'):raise ValueError('Frozen comparison policy changed')
    if 'explorationPolicy' in cfg and (not adaptive(cfg) or cfg['explorationPolicy']!=POLICY):raise ValueError('Unknown frozen exploration policy')
    if cfg['profile']=='bank' and cfg.get('taskFailurePolicy')!=TASK_FAILURE_POLICY:raise ValueError('Bank task failure policy changed')
    if cfg.get('canonicalJob'):
        from gepa_canonical import source_snapshot
        if cfg['canonicalSourceHash']!=source_snapshot(ROOT)[0]:raise ValueError('Canonical source inventory changed')
    repetitions=cfg.get('finalRepetitions',1)
    if type(repetitions) is not int or not 1<=repetitions<=3 or (repetitions>1 and not cfg.get('canonicalJob')):
        raise ValueError('Invalid frozen final repetition count')
    data=data_for(cfg);tasks={t['id']:(split,t) for split,rows in data.items() for t in rows}
    ledger=json.loads((directory/'gepa-rollouts.json').read_text());proposals=json.loads((directory/'gepa-proposals.json').read_text())
    search=json.loads((directory/'gepa-search.json').read_text());selection=json.loads((directory/'gepa-selection.json').read_text())
    selected=skill(search['candidates'][search['bestIndex']]['skill_body']);seed=cfg['baseline']['skill']
    if seed!=skill(seed['body']) or selected!=selection['skill'] or selection['bestIndex']!=search['bestIndex']:raise ValueError('Selected Skill changed')
    if not search['candidates'] or search['candidates'][0]!={'skill_body':seed['body']} or any(set(c)!={'skill_body'} for c in search['candidates']):raise ValueError('Unexpected optimized component')
    if len(proposals)>cfg['proposalBudget']:raise ValueError('Proposal budget exceeded')
    for p in proposals:
        if p['components']!=['skill_body'] or p['system']!=REFLECTION_SYSTEM or p['candidate']!={'skill_body':p['parentBody']}:raise ValueError('Reflection component drift')
        for trace in p['training']:
            if tasks.get(trace['taskId'],(None,))[0]!='train':raise ValueError('Reflection used non-training data')
        skill(p['body'])
    if any(c['skill_body']!=seed['body'] and c['skill_body'] not in [p['body'] for p in proposals] for c in search['candidates']):raise ValueError('Unproposed candidate entered GEPA search')
    totals={label:{split:[] for split in ('validation','heldout')} for label in ('baseline','selected')}
    reconstructed=[];search_rows=[]
    if progress_callback is not None:
        progress_callback(0, len(ledger))
    for i,row in enumerate(ledger):
        if row['id']!=f'R{i+1:04d}' or row['taskId'] not in tasks:raise ValueError('Invalid rollout identity')
        split,task=tasks[row['taskId']]
        if row['stage']=='search':
            if split=='heldout' or row['body'] not in [c['skill_body'] for c in search['candidates']]+[p['body'] for p in proposals]:raise ValueError('Search accessed final tasks or unknown Skill')
            search_rows.append(row)
        else:
            if (row['stage'] not in totals or split not in totals[row['stage']] or
                    row['body']!=(seed if row['stage']=='baseline' else selected)['body'] or
                    row['startedAt']<selection['frozenAt'] or
                    (repetitions>1 and (type(row.get('repetition')) is not int or
                                        not 0<=row['repetition']<(repetitions if split=='heldout' else 1)))):
                raise ValueError('Final task evaluated before selection, repetition identity or Skill drift')
        child=directory/'rollouts'/row['id'];result=verify_repair(child,child_config(cfg,task,row['body']))
        if result!=json.loads((child/'repair-evaluation.json').read_text()) or row['score']!=score(result) or row['evidenceHash']!=result['evidenceHash']:raise ValueError('Rollout score differs from trusted tests')
        if cfg['profile']=='bank' and any(row.get(k)!=result[k] for k in ('taskOutcome','sdkStopReason')):raise ValueError('Task outcome differs from verified SDK evidence')
        if row['stage']!='search':totals[row['stage']][split].append(row)
        calls=json.loads((child/'repair-calls.json').read_text())
        reconstructed.extend([{**c,'rolloutId':row['id'],'taskId':row['taskId'],'stage':row['stage']} for c in calls])
        if progress_callback is not None and ((i+1) % 3 == 0 or i+1 == len(ledger)):
            progress_callback(i+1, len(ledger))
    if len(search_rows)>cfg['metricBudget'] or search['metricCalls']!=len(search_rows):raise ValueError('GEPA metric accounting drift')
    if search['gepaVersion']!=GEPA_VERSION or search['sdkMetricCalls']!=len(search_rows):raise ValueError('Real optimizer accounting differs')
    scores=[]
    for candidate in search['candidates']:
        rows=[r for r in search_rows if r['body']==candidate['skill_body'] and tasks[r['taskId']][0]=='validation']
        # GEPA evaluates the seed and each accepted candidate on the full valset.
        by_task={r['taskId']:r['score'] for r in rows}
        if set(by_task)!={t['id'] for t in data['validation']}:raise ValueError('Candidate lacks full validation evidence')
        scores.append(sum(by_task.values())/len(by_task))
    if scores!=search['validationScores'] or search['bestIndex']!=max(range(len(scores)),key=lambda i:scores[i]):raise ValueError('Validation-selected candidate differs from evidence')
    final={}
    for label,splits in totals.items():
        final[label]={}
        for split,rows in splits.items():
            expected=sorted((t['id'],rep) for t in data[split] for rep in range(repetitions if split=='heldout' else 1))
            if sorted((r['taskId'],r.get('repetition',0)) for r in rows)!=expected:
                raise ValueError('Final evaluation is incomplete or duplicated')
            final[label][split]={'passed':sum(r['score'] for r in rows),'total':len(rows)}
    for i,p in enumerate(proposals):
        if p['id']!=f'P{i+1:03d}':raise ValueError('Proposal identity drift')
        if adaptive(cfg):
            duplicate=duplicate_of(p['body'],proposals[:i],seed['body'])
            if p.get('duplicateOf')!=duplicate or p.get('skippedEvaluations',0)!=(len(p['training']) if duplicate is not None else 0):raise ValueError('Early duplicate evidence drift')
        call=json.loads((directory/'reflections'/f'P{i+1:03d}'/'repair-calls.json').read_text())
        if len(call)!=1 or call[0]['request']['tools'] or call[0]['request']['messages']!=[{'role':'system','content':p['system']},{'role':'user','content':p['input']}]:raise ValueError('Reflection request drift')
        response=json.loads(call[0]['response']['choices'][0]['message']['content'])
        if response!={'skill_body':p['body']}:raise ValueError('Proposal differs from model completion')
        if json.loads(p['input'])!=proposal_context(p['candidate'],p['training'],proposals[:i],cfg):raise ValueError('Reflection input drift')
        for trace in p['training']:
            matches=[r for r in ledger if r['id']==trace['rolloutId'] and r['stage']=='search' and r['body']==p['parentBody'] and tasks[r['taskId']][0]=='train']
            if len(matches)!=1:raise ValueError('Reflection trajectory lacks training rollout evidence')
            child=directory/'rollouts'/trace['rolloutId']
            expected=training_trace(child,matches[0],tasks[matches[0]['taskId']][1])
            if trace!=expected:raise ValueError('Reflection feedback differs from trusted trace')
        reconstructed.append({**call[0],'proposalId':f'P{i+1:03d}','stage':'reflection'})
    reconstructed.sort(key=lambda c:c['startedAt'])
    actual=json.loads((directory/'gepa-calls.json').read_text())
    expected=[{**c,'id':i+1,'localId':c['id']} for i,c in enumerate(reconstructed)]
    if expected!=actual or len(actual)>cfg['callBudget']:raise ValueError('Global model call accounting drift')
    temperatures={p['id']:reflection_temperature(cfg,proposals[:i]) for i,p in enumerate(proposals)}
    for call in actual:
        if call['request'] != provider_payload(cfg['provider']['config'], call['request']):
            raise ValueError('GEPA provider reasoning settings changed')
        temperature=temperatures[call['proposalId']] if call.get('stage')=='reflection' else 0
        if call['status']!='completed' or call['request']['model']!=cfg['provider']['config']['model'] or type(call['request']['temperature']) not in (int,float) or call['request']['temperature']!=temperature or call['request']['max_tokens']!=cfg['provider']['config']['maxTokens']:raise ValueError('Model settings changed or request failed')
        if 'streamEvents' in call:
            acc=ToolAccumulator()
            for e in call['streamEvents']:acc.add(e)
            if acc.reply()!=call['response']:raise ValueError('Stream evidence drift')
    comparison=paired_final(data,ledger,repetitions) if cfg.get('comparisonPolicy')==COMPARISON_POLICY else None
    blockers=release_blockers(cfg.get('comparisonPolicy'),seed,selected,final,comparison)
    eligible=not blockers
    decision(cfg['logRoot'],'M5','gepa.release-gate','eligible' if eligible else 'withheld',identifier=directory.name,
             blockers=len(blockers),regressed=sum(comparison['splits'][s]['regressed'] for s in ('validation','heldout')) if comparison else 0,
             rollouts=len(ledger),calls=len(actual))
    hashes={p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file() and (p.name.startswith(('gepa-','repair-')) and not p.name.endswith('progress.json')) and p.name not in ('gepa-evaluation.json','gepa-selection.md')}
    return {'engine':ENGINE,'checksPassed':True,'eligible':eligible,'selectedSkill':selected,'baselineSkill':seed,'final':final,
      'metricEvaluations':len(search_rows),'rollouts':len(ledger),'proposals':len(proposals),'calls':len(actual),'validationScores':scores,
      'gepaVersion':GEPA_VERSION,'sdkVersion':cfg['sdk']['version'],'datasetVersion':cfg['provenance']['datasetVersion'],'evidenceHash':digest(hashes),
      **({'comparison':comparison,'releaseBlockers':blockers} if comparison else {}),
      **({'breakdown':breakdown(ledger,tasks),'taskFailures':[{'rolloutId':r['id'],'taskId':r['taskId'],'stage':r['stage'],'reason':r['sdkStopReason']} for r in ledger if r.get('taskOutcome')=='call-limit']} if cfg['profile']=='bank' else {}),
      **({'exploration':summary(cfg,ledger,proposals,search['candidates'])} if exploring(cfg) else {})}

def breakdown(ledger,tasks):
    result={}
    for dimension in ('difficulty','topic'):
        table={}
        for row in ledger:
            if row['stage']=='search':continue
            split,task=tasks[row['taskId']];key=task[dimension]
            counts=table.setdefault(key,{label:{s:{'passed':0,'total':0} for s in ('validation','heldout')} for label in ('baseline','selected')})[row['stage']][split]
            counts['total']+=1;counts['passed']+=row['score']
        result[dimension]=table
    return result

def training_trace(child,row,task):
    result=json.loads((child/'repair-evaluation.json').read_text())
    tools=json.loads((child/'repair-tools.json').read_text())
    feedback,safe_tools=training_feedback(result,tools)
    return {'rolloutId':row['id'],'taskId':task['id'],'task':task['fixture']['prompt'],'score':row['score'],
      'source':(child/'repair-candidate.py').read_bytes().decode('utf-8'),
      'feedback':feedback,'tools':safe_tools,
      **({'taskOutcome':result['taskOutcome'],'sdkStopReason':result['sdkStopReason']} if 'taskOutcome' in result else {})}
