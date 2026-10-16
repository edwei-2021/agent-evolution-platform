"""Server-owned bounded repair configuration, separate from Skill evolution."""
from repair_runtime import sdk_status
from repair_engine import ENGINE, provenance
from repair_fixture import SKILL, TASK_ID

class RepairStore:
    def __init__(self,service):self.service=service
    def freeze(self,options):
        import time
        fields={'maxSeconds','callTimeoutSeconds','callBudget','providerRevision'}
        if not isinstance(options,dict) or set(options)!=fields:raise ValueError('Use repair time/call budgets and current providerRevision')
        for key,low,high in [('maxSeconds',60,7200),('callTimeoutSeconds',10,3600),('callBudget',2,12)]:
            if type(options[key]) is not int or not low<=options[key]<=high:raise ValueError(f'{key} must be an integer in {low}..{high}')
        sdk=sdk_status(self.service.root)
        if not sdk['available']:raise RuntimeError(sdk['error'])
        with self.service.ollama.lock:provider=self.service.ollama.frozen()
        if type(options['providerRevision']) is not int or options['providerRevision']!=provider['revision']:raise RuntimeError('Provider settings changed; refresh first')
        if not provider['config']['model']:raise ValueError('Select and save a model first')
        return {'engine':ENGINE,'taskId':TASK_ID,'skill':SKILL,'sdk':sdk,'provider':{**provider,'endpoint':provider['endpoint']},
                'maxSeconds':options['maxSeconds'],'deadlineEpoch':time.time()+options['maxSeconds'],'callBudget':options['callBudget'],
                'callTimeoutSeconds':min(options['callTimeoutSeconds'],provider['config']['inferenceTimeout']),
                'toolBudget':24,'provenance':provenance()}
