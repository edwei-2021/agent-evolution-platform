"""Supplementary generation evidence; never changes model dispatch or scoring."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path


def stamp():
    return datetime.now(timezone.utc).isoformat()


def text_hash(body):
    return hashlib.sha256(body.encode()).hexdigest()


def conditions(config, component):
    provenance = config.get('provenance', {})
    provider = config.get('provider', {}).get('config', {})
    hashes={**provenance.get('repair',{}).get('codeHashes',{}),**provenance.get('codeHashes',{})}
    for name,key in (('skill_engine.py','evaluatorHash'),('skill_agents.py','runnerHash'),('runtime_service.py','runtimeHash'),('skill_audit.py','auditHash')):
        if key in provenance:hashes[name]=provenance[key]
    return {'component': component, 'profile': config.get('profile'),
            'baselineVersionId': config.get('baseline', {}).get('id'),
            'datasetVersion': provenance.get('datasetVersion', provenance.get('datasetRevision')),
            'datasetHash': provenance.get('datasetHash'),
            'bankRevision': config.get('bankRevision'), 'sdkVersion': config.get('sdk',{}).get('version'),
            'optimizerVersion': config.get('optimizer',{}).get('version'),
            'codeHashes': hashes,
            'model': provider.get('model'), 'provider': provider.get('provider', 'ollama') if provider else None,
            'reasoningEffort': provider.get('reasoningEffort'), 'outputLimit': provider.get('maxTokens'),
            'temperature': 0 if provider else None,
            'limits': {key: config.get(key) for key in ('metricBudget', 'proposalBudget', 'taskCallBudget',
                       'callBudget', 'maxSeconds', 'callTimeoutSeconds', 'maxCandidates')},
            'seed': None,
            'reflectionBatch': config.get('reflectionBatch'),
            'trigger': 'training-feedback-only'}


def feedback_refs(training):
    result=[]
    for row in training[:30]:
        if not isinstance(row,dict):
            continue
        item={}
        task_id=row.get('taskId',row.get('id'))
        if isinstance(task_id,str):
            item['taskId']=task_id[:120]
        if isinstance(row.get('rolloutId'),str):
            item['rolloutId']=row['rolloutId'][:16]
        if type(row.get('score')) in (int,float) and 0<=row['score']<=1:
            item['score']=row['score']
        if type(row.get('passed')) is bool:
            item['passed']=row['passed']
        if type(row.get('callId')) is int:
            item['callId']=row['callId']
        if row.get('taskOutcome') in ('completed','call-limit'):
            item['taskOutcome']=row['taskOutcome']
        result.append(item)
    return result


def save(path, value):
    """Audit I/O failure stays separate from authoritative execution evidence."""
    try:
        from skill_engine import write
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, value)
        return True
    except (OSError, ValueError, TypeError):
        return False


class Generation:
    def __init__(self, directory, identifier, config, parent, training, component, **extra):
        self.path = Path(directory)/'skill-audit'/(identifier+'.json')
        self.value = {'schemaVersion': 1, 'id': identifier, 'status': 'started', 'startedAt': stamp(),
                      'finishedAt': None, 'parent': parent, 'candidate': None,
                      'conditions': conditions(config, component) | extra,
                      'trainingRefs': feedback_refs(training), 'errorType': None}

    def __enter__(self):
        # A proposal identity belongs to one run; never overwrite an older attempt.
        self.owned = not self.path.exists()
        if self.owned:
            save(self.path, self.value)
        return self

    def capture(self, body):
        if isinstance(body, str):
            self.value['candidate'] = {'body': body if len(body.encode()) <= 16000 else None,
                                       'bodyHash': text_hash(body), 'bytes': len(body.encode()), 'hash': None}
            self.value['status'] = 'returned'
            if self.owned:
                save(self.path, self.value)

    def generated(self, skill):
        self.value['candidate'] = dict(skill, bodyHash=text_hash(skill['body']))
        self.value['status'] = 'generated'
        if self.owned:
            save(self.path, self.value)

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self.value['status'] = 'failed'
            self.value['errorType'] = kind.__name__
        self.value['finishedAt'] = stamp()
        if self.owned:
            save(self.path, self.value)
        return False
