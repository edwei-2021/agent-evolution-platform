"""Trusted GEPA evidence contracts; imports no optimizer in the GUI process."""
from step_trace import traced
import hashlib
import json
from pathlib import Path
from repair_engine import provenance as repair_provenance, verify as verify_repair, ROOT
from repair_fixture import digest, TOOLS
from repair_transport import ToolAccumulator
from gepa_dataset import dataset, dataset_hash, skill, DATASET_VERSION
from gepa_runtime import GEPA_VERSION
from skill_engine import write

ENGINE='gepa-nanobot-repair-v1'
TASKS={'coordinator':'Freeze grouped benchmark and search budgets','worker':'Run real GEPA with fresh nanobot rollouts',
       'reflector':'Freeze the validation-selected Skill','evaluator':'Evaluate frozen baseline/selected Skills on final data','reviewer':'Replay trusted evidence and review release gates'}
REFLECTION_SYSTEM='Improve only the generic Python repair Skill body using the supplied training trajectories. Do not output solution code or modify Skill name/description. Return exactly a JSON object with one string field: skill_body. Keep instructions general; do not embed task IDs or test answers.'

def provenance(profile):
    return {'engine':ENGINE,'gepaVersion':GEPA_VERSION,'datasetVersion':DATASET_VERSION,'datasetHash':dataset_hash(profile),'repair':repair_provenance(),
      'codeHashes':{n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ('gepa_dataset.py','gepa_engine.py','gepa_sdk.py','gepa_agents.py')}}

def progress(directory,**changes):
    p=directory/'gepa-progress.json';data=json.loads(p.read_text()) if p.exists() else {'engine':ENGINE,'phase':'queued','calls':0,'completedCalls':0,'failedCalls':0,'metricEvaluations':0,'proposals':0,'rollouts':0,'lastCall':None}
    data.update(changes);write(p,data);return data

def child_config(cfg,task,body):
    return {'engine':'nanobot-python-repair-v1','taskId':task['id'],'skill':skill(body),'fixture':task['fixture'],
      'sdk':cfg['sdk'],'provider':cfg['provider'],'maxSeconds':cfg['maxSeconds'],'deadlineEpoch':cfg['deadlineEpoch'],
      'callBudget':cfg['taskCallBudget'],'callTimeoutSeconds':cfg['callTimeoutSeconds'],'toolBudget':24,
      'provenance':cfg['provenance']['repair'],'logRoot':cfg['logRoot'],'correlationRunId':cfg['runId']}

def score(result):
    return int(result['repairPassed'])

@traced('gepa','evidence.verify')
def verify(directory):
    directory=Path(directory);cfg=json.loads((directory/'gepa-config.json').read_text())
    if cfg['provenance']!=provenance(cfg['profile']):raise ValueError('GEPA code or dataset provenance changed')
    data=dataset(cfg['profile']);tasks={t['id']:(split,t) for split,rows in data.items() for t in rows}
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
    for i,row in enumerate(ledger):
        if row['id']!=f'R{i+1:04d}' or row['taskId'] not in tasks:raise ValueError('Invalid rollout identity')
        split,task=tasks[row['taskId']]
        if row['stage']=='search':
            if split=='heldout' or row['body'] not in [c['skill_body'] for c in search['candidates']]+[p['body'] for p in proposals]:raise ValueError('Search accessed final tasks or unknown Skill')
            search_rows.append(row)
        else:
            if row['stage'] not in totals or split not in totals[row['stage']] or row['body']!=(seed if row['stage']=='baseline' else selected)['body'] or row['startedAt']<selection['frozenAt']:raise ValueError('Final task evaluated before selection or Skill drift')
        child=directory/'rollouts'/row['id'];result=verify_repair(child,child_config(cfg,task,row['body']))
        if result!=json.loads((child/'repair-evaluation.json').read_text()) or row['score']!=score(result) or row['evidenceHash']!=result['evidenceHash']:raise ValueError('Rollout score differs from trusted tests')
        if row['stage']!='search':totals[row['stage']][split].append(row)
        calls=json.loads((child/'repair-calls.json').read_text())
        reconstructed.extend([{**c,'rolloutId':row['id'],'taskId':row['taskId'],'stage':row['stage']} for c in calls])
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
            if sorted(r['taskId'] for r in rows)!=sorted(t['id'] for t in data[split]):raise ValueError('Final evaluation is incomplete or duplicated')
            final[label][split]={'passed':sum(r['score'] for r in rows),'total':len(rows)}
    for i,p in enumerate(proposals):
        call=json.loads((directory/'reflections'/f'P{i+1:03d}'/'repair-calls.json').read_text())
        if len(call)!=1 or call[0]['request']['tools'] or call[0]['request']['messages']!=[{'role':'system','content':p['system']},{'role':'user','content':p['input']}]:raise ValueError('Reflection request drift')
        response=json.loads(call[0]['response']['choices'][0]['message']['content'])
        if response!={'skill_body':p['body']}:raise ValueError('Proposal differs from model completion')
        if json.loads(p['input'])!={'candidate':p['candidate'],'training':p['training']}:raise ValueError('Reflection input drift')
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
    for call in actual:
        if call['status']!='completed' or call['request']['model']!=cfg['provider']['config']['model'] or call['request']['temperature']!=0 or call['request']['max_tokens']!=cfg['provider']['config']['maxTokens']:raise ValueError('Model settings changed or request failed')
        if 'streamEvents' in call:
            acc=ToolAccumulator()
            for e in call['streamEvents']:acc.add(e)
            if acc.reply()!=call['response']:raise ValueError('Stream evidence drift')
    eligible=selected['hash']!=seed['hash'] and final['selected']['validation']['passed']>final['baseline']['validation']['passed'] and final['selected']['heldout']['passed']>=final['baseline']['heldout']['passed']
    hashes={p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file() and (p.name.startswith(('gepa-','repair-')) and not p.name.endswith('progress.json')) and p.name not in ('gepa-evaluation.json','gepa-selection.md')}
    return {'engine':ENGINE,'checksPassed':True,'eligible':eligible,'selectedSkill':selected,'baselineSkill':seed,'final':final,
      'metricEvaluations':len(search_rows),'rollouts':len(ledger),'proposals':len(proposals),'calls':len(actual),'validationScores':scores,
      'gepaVersion':GEPA_VERSION,'sdkVersion':cfg['sdk']['version'],'datasetVersion':DATASET_VERSION,'evidenceHash':digest(hashes)}

def training_trace(child,row,task):
    result=json.loads((child/'repair-evaluation.json').read_text())
    tools=json.loads((child/'repair-tools.json').read_text())
    return {'rolloutId':row['id'],'taskId':task['id'],'task':task['fixture']['prompt'],'score':row['score'],
      'source':(child/'repair-candidate.py').read_bytes().decode('utf-8'),
      'feedback':result['candidate'],'tools':[{'name':t['name'],'status':t['status'],'result':t.get('result'),'error':t.get('error')} for t in tools]}
