"""Model-facing feedback: public source, counts and fixed failure categories."""
import json

POLICY = 'count-only-training-feedback-v1'
TOOLS = {'read_solution', 'write_solution', 'run_tests'}


def counts(value):
    if not isinstance(value, dict):
        raise ValueError('Missing trusted training counts')
    p, n = value.get('passed'), value.get('total')
    if type(p) is not int or type(n) is not int or not 0 <= p <= n <= 50 or n == 0:
        raise ValueError('Invalid trusted training counts')
    return {'passed': p, 'total': n}


def training_feedback(evaluation, tools):
    """Exclude retained examples, raw tool bodies, exception text and paths."""
    feedback = {split: counts(evaluation['candidate'][split]) for split in ('visible', 'hidden')}
    records = []
    for tool in tools:
        name, status = tool.get('name'), tool.get('status')
        if name not in TOOLS or status not in ('completed', 'failed'):
            raise ValueError('Incomplete training tool evidence')
        row = {'name': name, 'status': status, 'result': None, 'error': None}
        if status == 'failed':
            row['error'] = 'tool-policy-or-validation-rejection'
        elif name == 'run_tests':
            row['result'] = json.dumps(counts(json.loads(tool['result'])), sort_keys=True)
        records.append(row)
    return feedback, records
