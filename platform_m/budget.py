"""Checkpointable budget accounting with distinct task/reflection/model ceilings."""
from .evidence import digest

class Budget:
    def __init__(self, ceilings, checkpoint=None):
        required = {'search_tasks', 'final_tasks', 'reflections', 'model_calls', 'output_tokens'}
        if set(ceilings) != required or any(type(n) is not int or n < 1 for n in ceilings.values()):
            raise ValueError('Every budget ceiling must be a positive integer')
        self.ceilings = dict(ceilings)
        self.consumed = {key: 0 for key in ceilings}
        self.completed = {}
        if checkpoint is not None:
            if checkpoint['ceilings'] != ceilings:
                raise ValueError('Resume budget changed')
            self.consumed, self.completed = checkpoint['consumed'], checkpoint['completed']
            if set(self.consumed) != required or any(type(n) is not int or not 0 <= n <= ceilings[k]
                                                    for k, n in self.consumed.items()):
                raise ValueError('Invalid budget checkpoint')
    def reserve(self, key, charges, snapshot):
        marker = digest({'charges': charges, 'snapshot': snapshot})
        if key in self.completed:
            if self.completed[key]['snapshot'] != marker:
                raise ValueError('Completed task snapshot changed')
            if self.completed[key]['result'] is None:
                raise RuntimeError('Ambiguous pending request; inspect evidence before authorizing another attempt')
            return False
        if not charges or set(charges)-set(self.ceilings) or any(type(n) is not int or n < 0 for n in charges.values()):
            raise ValueError('Invalid budget charge')
        if any(self.consumed[k]+n > self.ceilings[k] for k, n in charges.items()):
            raise ValueError('Budget exhausted before dispatch')
        for k, n in charges.items():
            self.consumed[k] += n
        self.completed[key] = {'snapshot': marker, 'result': None}
        return True
    def finish(self, key, result_hash):
        if self.completed[key]['result'] not in (None, result_hash):
            raise ValueError('Result cannot change after completion')
        self.completed[key]['result'] = result_hash
    def snapshot(self):
        return {'ceilings': self.ceilings, 'consumed': self.consumed, 'completed': self.completed}
