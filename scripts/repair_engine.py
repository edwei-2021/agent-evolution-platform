"""Trusted bounded task preparation, tool mediation, replay and evaluation."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from repair_fixture import BASELINE, SKILL, PROMPT, TASK_ID, TOOLS, VISIBLE, HIDDEN, digest, validate_source
from skill_engine import write
from repair_transport import ToolAccumulator
from llm_transport import stream_chat
from debug_log import DebugLog
from repair_runtime import SDK_VERSION

ROOT=Path(__file__).resolve().parents[1]
ENGINE='nanobot-python-repair-v1'
TASKS={'coordinator':'Freeze fixture and prepare fresh task workspace','worker':'Run bounded nanobot SDK tool loop',
       'reflector':'Summarize recorded tools without model calls','evaluator':'Run trusted visible and hidden tests','reviewer':'Replay evidence and verify independent results'}

def provenance():
    return {'engine':ENGINE,'taskId':TASK_ID,'fixtureHash':digest({'baseline':BASELINE,'visible':VISIBLE,'hidden':HIDDEN,'prompt':PROMPT}),
            'skillHash':digest(SKILL),'sdkVersion':SDK_VERSION,'codeHashes':{n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest()
            for n in ('repair_fixture.py','repair_engine.py','repair_evaluator.py','repair_sdk.py','repair_agents.py','repair_transport.py','llm_transport.py')}}

def progress(directory,**changes):
    path=directory/'repair-progress.json'
    data=json.loads(path.read_text()) if path.exists() else {'engine':ENGINE,'phase':'queued','calls':0,'completedCalls':0,'failedCalls':0,'toolCalls':0,'lastCall':None}
    data.update(changes);write(path,data);return data

def trusted_test(source,split,fixture=None):
    command=[sys.executable,'-I','-S',str(ROOT/'scripts/repair_evaluator.py')]
    result=subprocess.run(command,input=json.dumps({'source':source,'split':split,**({'fixture':fixture} if fixture is not None else {})}),text=True,capture_output=True,timeout=5)
    try: data=json.loads(result.stdout)
    except ValueError:raise ValueError('Trusted evaluator returned no structured evidence')
    if result.returncode or data.get('error'):raise ValueError(data.get('error','Trusted evaluator failed'))
    return data

class RepairRunner:
    def __init__(self,directory,config):
        self.directory=Path(directory);self.config=config;self.calls=[];self.tools=[]
        self.logs=DebugLog(config.get('logRoot',self.directory.parents[2]));self.workspace=self.directory/'task-workspace'
    def publish(self,**changes):
        return progress(self.directory,**changes)
    def path(self,path):
        if path!='solution.py':raise ValueError('Only solution.py is accessible')
        if self.workspace.is_symlink() or self.workspace.resolve()!=self.directory.resolve()/'task-workspace':raise ValueError('Workspace must remain inside its run directory')
        target=self.workspace/path
        if target.is_symlink() or target.resolve()!=self.workspace.resolve()/'solution.py':raise ValueError('External paths and symlinks are forbidden')
        return target
    def tool(self,name,arguments):
        if name not in TOOLS or not isinstance(arguments,dict):raise ValueError('Unsupported repair tool')
        if len(self.tools)>=24:raise RuntimeError('Tool execution budget exhausted')
        expected={'path','source'} if name=='write_solution' else {'path'} if name=='read_solution' else set()
        if set(arguments)!=expected:raise ValueError('Unexpected tool arguments')
        record={'id':len(self.tools)+1,'name':name,'arguments':arguments,'startedAt':time.time(),'status':'running'}
        self.tools.append(record)
        try:
            if name=='read_solution':result=self.path(arguments['path']).read_bytes().decode('utf-8')
            elif name=='write_solution':
                validate_source(arguments['source']);self.path(arguments['path']).write_text(arguments['source']);result='Updated solution.py; independent tests still required.'
            else:result=json.dumps(trusted_test(self.path('solution.py').read_bytes().decode('utf-8'),'visible',self.config.get('fixture')))
            record.update(status='completed',result=result);return result
        except Exception as exc:record.update(status='failed',error=str(exc));raise
        finally:
            record['finishedAt']=time.time();write(self.directory/'repair-tools.json',self.tools)
            self.publish(toolCalls=len(self.tools),lastTool={'name':name,'status':record['status']})
            self.logs.append('nanobot','ERROR' if record['status']=='failed' else 'INFO','Tool '+name+' '+record['status'],self.config.get('correlationRunId',self.directory.name))

    def call(self,messages,tools):
        cfg=self.config
        if len(self.calls)>=cfg['callBudget'] or time.time()>=cfg['deadlineEpoch']:raise RuntimeError('Repair model call/time budget exhausted')
        grants=() if cfg.get('reflectionOnly') else TOOLS
        if sorted(t['function']['name'] for t in tools)!=sorted(grants):raise ValueError('SDK requested an unexpected tool grant')
        settings={**cfg['provider']['config'],'inferenceTimeout':min(cfg['callTimeoutSeconds'],cfg['provider']['config']['inferenceTimeout'],max(1,int(cfg['deadlineEpoch']-time.time())))}
        payload={'model':settings['model'],'messages':messages,'tools':tools,'stream':True,'temperature':0,'max_tokens':settings['maxTokens']}
        if len(json.dumps(payload))>200000:raise ValueError('Repair request exceeds size limit')
        record={'id':len(self.calls)+1,'kind':'gepa-skill-reflection' if cfg.get('reflectionOnly') else 'nanobot-tool-turn','status':'running','startedAt':time.time(),
            'timeoutSeconds':settings['inferenceTimeout'],'deadlineEpoch':time.time()+settings['inferenceTimeout'],'request':payload,'chunks':0,'outputChars':0,'reasoningChars':0}
        self.calls.append(record);write(self.directory/'repair-calls.json',self.calls)
        def publish():self.publish(calls=len(self.calls),completedCalls=sum(c['status']=='completed' for c in self.calls),failedCalls=sum(c['status']=='failed' for c in self.calls),lastCall={k:v for k,v in record.items() if k not in ('request','response','streamEvents')})
        publish();self.logs.append('nanobot','INFO',f'Model call #{record["id"]} started',self.config.get('correlationRunId',self.directory.name),{'model':settings['model'],'timeoutSeconds':record['timeoutSeconds']})
        last_update=time.monotonic()
        def update(changes):
            nonlocal last_update
            first=changes.get('lastChunkAt') and not record.get('firstChunkAt');record.update(changes)
            if first:record['firstChunkAt']=changes['lastChunkAt']
            if first or 'responseStartedAt' in changes or time.monotonic()-last_update>=1:publish();last_update=time.monotonic()
        try:
            record['response'],events=stream_chat(cfg['provider']['endpoint'],settings,payload,update,ToolAccumulator)
            if events is not None:record['streamEvents']=events
            message=record['response']['choices'][0]['message'];calls=message.get('tool_calls',[])
            if not isinstance(calls,list) or len(calls)>8:raise ValueError('Malformed tool call list')
            ids=set()
            for call in calls:
                if call.get('type')!='function' or not isinstance(call.get('id'),str) or not call['id'] or call['id'] in ids:raise ValueError('Malformed or duplicate tool call ID')
                ids.add(call['id']);fn=call['function']
                if fn['name'] not in grants:raise ValueError('Model requested an ungranted tool: '+str(fn['name']))
                args=json.loads(fn['arguments'])
                if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
            if not calls and (not isinstance(message.get('content'),str) or not message['content'].strip()):raise ValueError('Empty final response is not accepted')
            record['status']='completed';return record['response']
        except Exception as exc:record.update(status='failed',error=str(exc));raise
        finally:
            record.update(finishedAt=time.time(),elapsedMs=round((time.time()-record['startedAt'])*1000,3))
            write(self.directory/'repair-calls.json',self.calls);publish()
            self.logs.append('nanobot','ERROR' if record['status']=='failed' else 'INFO',f'Model call #{record["id"]} {record["status"]}'+(': '+record['error'] if record.get('error') else ''),self.config.get('correlationRunId',self.directory.name),{'elapsedMs':record['elapsedMs'],'chunks':record['chunks']})

def evidence(directory):
    names=('repair-config.json','repair-calls.json','repair-tools.json','repair-sdk-result.json','repair-baseline.py','repair-candidate.py','repair-reflection.json')
    return digest({n:hashlib.sha256((directory/n).read_bytes()).hexdigest() for n in names})

def verify(directory,expected_config=None):
    cfg=json.loads((directory/'repair-config.json').read_text())
    if cfg['provenance']!=provenance() or (expected_config is None and (cfg['skill']!=SKILL or 'fixture' in cfg)) or (expected_config is not None and cfg!=expected_config):raise ValueError('Repair code, fixture or skill provenance changed')
    fixture=cfg.get('fixture');baseline_source=fixture['baseline'] if fixture else BASELINE
    prompt=fixture['prompt'] if fixture else PROMPT
    calls=json.loads((directory/'repair-calls.json').read_text());tools=json.loads((directory/'repair-tools.json').read_text())
    if not 1<=len(calls)<=cfg['callBudget'] or len(tools)>24:raise ValueError('Invalid repair call/tool accounting')
    for i,c in enumerate(calls):
        if c['id']!=i+1 or c['status']!='completed' or c['request']['model']!=cfg['provider']['config']['model'] or c['request']['temperature']!=0 or c['request']['max_tokens']!=cfg['provider']['config']['maxTokens'] or sorted(t['function']['name'] for t in c['request']['tools'])!=sorted(TOOLS):raise ValueError('Repair request drift or failed call')
        if 'streamEvents' in c:
            acc=ToolAccumulator()
            for event in c['streamEvents']:acc.add(event)
            if acc.reply()!=c['response']:raise ValueError('Repair stream evidence differs from completion')
    candidate=(directory/'repair-candidate.py').read_bytes().decode('utf-8');validate_source(candidate)
    if (directory/'repair-baseline.py').read_bytes().decode('utf-8')!=baseline_source:raise ValueError('Baseline artifact changed')
    if (directory/'task-workspace/solution.py').is_symlink() or candidate!=(directory/'task-workspace/solution.py').read_bytes().decode('utf-8'):raise ValueError('Final solution changed after freezing')
    # Replay successful writes and visible test tools; model assertions never score.
    replay=baseline_source
    requested=[]
    for c in calls:
        for t in c['response']['choices'][0]['message'].get('tool_calls',[]):
            requested.append((t['function']['name'],json.loads(t['function']['arguments']),c['finishedAt']))
    request_position=0
    for i,t in enumerate(tools):
        if t['id']!=i+1 or t['name'] not in TOOLS:raise ValueError('Invalid tool trace')
        while request_position<len(requested) and requested[request_position][:2]!=(t['name'],t['arguments']):request_position+=1
        if request_position==len(requested) or t['startedAt']<requested[request_position][2] or t['finishedAt']<t['startedAt']:raise ValueError('Executed tool differs from recorded model request')
        request_position+=1
        if t['status']=='completed':
            if t['name']=='write_solution':
                if t['arguments']['path']!='solution.py':raise ValueError('Tool path drift')
                validate_source(t['arguments']['source']);replay=t['arguments']['source']
            elif t['name']=='read_solution' and (t['arguments']!={'path':'solution.py'} or t['result']!=replay):raise ValueError('Read evidence drift')
            elif t['name']=='run_tests' and (t['arguments'] or json.loads(t['result'])!=trusted_test(replay,'visible',fixture)):raise ValueError('Visible test evidence drift')
    if replay!=candidate:raise ValueError('Candidate differs from recorded writes')
    sdk=json.loads((directory/'repair-sdk-result.json').read_text())
    if sdk['sdkVersion']!=SDK_VERSION or sdk.get('error') or sdk['stopReason']!='completed' or sdk['grantedTools']!=list(TOOLS):raise ValueError('SDK did not complete successfully')
    initial='\n'.join(m.get('content','') for m in calls[0]['request']['messages'] if isinstance(m.get('content'),str))
    if prompt not in initial or cfg['skill']['body'] not in initial:raise ValueError('Initial task or fixed Skill drift')
    baseline={split:trusted_test(baseline_source,split,fixture) for split in ('visible','hidden')}
    after={split:trusted_test(candidate,split,fixture) for split in ('visible','hidden')}
    patch=''.join(difflib.unified_diff(baseline_source.splitlines(keepends=True),candidate.splitlines(keepends=True),fromfile='a/solution.py',tofile='b/solution.py'))
    if (directory/'repair-change.patch').exists() and (directory/'repair-change.patch').read_bytes().decode('utf-8')!=patch:raise ValueError('Patch artifact differs from verified source')
    return {'engine':ENGINE,'checksPassed':True,'taskId':cfg['taskId'],'baseline':baseline,'candidate':after,
            'repairPassed':all(m['passed']==m['total'] for m in after.values()),'calls':len(calls),'toolCalls':len(tools),
            'candidateHash':hashlib.sha256(candidate.encode()).hexdigest(),'patchHash':hashlib.sha256(patch.encode()).hexdigest(),'evidenceHash':evidence(directory),
            'sdkVersion':SDK_VERSION,'decision':'verified-task-result-only; no skill activation'}
