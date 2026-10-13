"""Bounded structured step spans over the existing failure-isolated journal."""
from datetime import datetime,timezone
from functools import wraps
import inspect
import json
from pathlib import Path
import time
import uuid
from debug_log import DebugLog,redact

class Step:
    def __init__(self,logs,module,name,run_id=None,**details):
        self.logs=logs;self.module=module;self.name=name;self.run_id=run_id;self.details=details
        self.id=uuid.uuid4().hex;self.started=time.perf_counter();self.finished=False
        self.emit('STEP_STARTED')
    def emit(self,event,**details):
        # Instrumentation must never change evaluation or dispatch semantics.
        try:self.logs.append(self.module,'ERROR' if event=='STEP_FAILED' else 'WARNING' if event in ('STEP_CANCELLED','STEP_INTERRUPTED') else 'INFO',
          f'{event} {self.name}',self.run_id,{'event':event,'stepId':self.id,'step':self.name,**self.details,**details})
        except (OSError,ValueError):pass
    def finish(self,status='completed',error=None):
        if self.finished:return
        self.finished=True
        event={'completed':'STEP_COMPLETED','failed':'STEP_FAILED','cancelled':'STEP_CANCELLED','interrupted':'STEP_INTERRUPTED'}[status]
        self.emit(event,durationMs=round((time.perf_counter()-self.started)*1000,3),**({'error':redact(error)} if error else {}))
    def __enter__(self):return self
    def __exit__(self,kind,value,tb):self.finish('failed' if kind else 'completed',str(value) if kind else None)

def context(directory,config=None):
    directory=Path(directory)
    if config is None:
        config={}
        for name in ('gepa-config.json','repair-config.json','llm-config.json','skill-config.json'):
            path=directory/name
            if path.is_file():
                try:config=json.loads(path.read_text())
                except (OSError,ValueError):pass
                break
    root=config.get('logRoot',directory.parents[2])
    run_id=config.get('correlationRunId',config.get('runId',directory.name))
    return DebugLog(root),run_id

def traced(module,name):
    """Trace sync/async functions and methods without logging argument bodies."""
    def decorate(fn):
        signature=inspect.signature(fn)
        def begin(args,kwargs):
            bound=signature.bind(*args,**kwargs).arguments;obj=bound.get('self')
            owner=getattr(obj,'session',obj)
            directory=bound.get('directory',getattr(obj,'directory',getattr(owner,'directory',None)))
            config=bound.get('config',bound.get('cfg',getattr(obj,'config',getattr(owner,'config',getattr(owner,'cfg',None)))))
            # Model runners already own a journal. Reuse it instead of running
            # schema/index initialization for every nested span and model call.
            logs = getattr(getattr(owner, 'client', None), 'logs', None)
            expected_root = (config or {}).get('logRoot', directory.parents[2])
            if logs is not None and logs.path == Path(expected_root) / '.local/debug.sqlite3':
                run_id = (config or {}).get('correlationRunId', (config or {}).get('runId', directory.name))
            else:
                logs,run_id=context(directory,config)
            details={k:bound[k] for k in ('role','stage','split') if isinstance(bound.get(k),str)}
            if isinstance(bound.get('name'),str):details['toolName']=bound['name']
            if isinstance(bound.get('task'),dict):details['taskId']=bound['task'].get('id')
            if directory.name.startswith(('R0','P0')):details['artifactId']=directory.name
            return Step(logs,module,name,run_id,**details)
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_call(*args,**kwargs):
                with begin(args,kwargs):return await fn(*args,**kwargs)
            return async_call
        @wraps(fn)
        def call(*args,**kwargs):
            with begin(args,kwargs):return fn(*args,**kwargs)
        return call
    return decorate

def snapshot(service,run_id):
    run=service.get_run(run_id)
    page=service.logs.list(run_id=run_id,query='STEP_',limit=500)
    spans={}
    for record in reversed(page['records']):
        d=record['details'];identifier=d.get('stepId');event=d.get('event')
        if not isinstance(identifier,str) or len(identifier)!=32 or event not in ('STEP_STARTED','STEP_COMPLETED','STEP_FAILED','STEP_CANCELLED','STEP_INTERRUPTED'):continue
        span=spans.setdefault(identifier,{'id':identifier,'name':d.get('step','unknown'),'module':record['module'],'status':'running','startedAt':None,'finishedAt':None,'durationMs':None})
        span.update({k:d[k] for k in ('role','stage','taskId','artifactId','toolName') if k in d})
        if event=='STEP_STARTED':span['startedAt']=record['at']
        else:
            span.update(status=event.removeprefix('STEP_').lower(),finishedAt=record['at'],durationMs=d.get('durationMs'),error=d.get('error'))
    if run['status'] not in ('queued','running'):
        for span in spans.values():
            if span['status']=='running':span['status']='unreported'
    steps=sorted(spans.values(),key=lambda s:s['startedAt'] or s['finishedAt'] or '',reverse=True)
    return {'schemaVersion':1,'runId':run_id,'runStatus':run['status'],'steps':steps,'returnedEvents':len(page['records']),
      'matchedEvents':page['matched'],'truncated':page['nextBefore'] is not None,'serverTime':page['serverTime']}
