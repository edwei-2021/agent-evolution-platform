"""Model-facing feedback: public source, counts and fixed failure categories."""
import json

POLICY = 'bounded-policy-categories-v2'
TOOLS = {'read_solution', 'write_solution', 'run_tests'}

# Only fixed, model-actionable categories cross the training feedback boundary.
# Tool errors can contain source text, paths or provider details; never forward
# arbitrary exception messages into a reflection request.
WRITE_REJECTIONS = (
    ('Unavailable call: isinstance ', 'disallowed-isinstance: use the declared input shape and explicit conditions'),
    ('Unavailable call: type ', 'disallowed-type: use the declared input shape and explicit conditions'),
    ('Only the reverse keyword is available', 'disallowed-keyword: use only reverse= or explicit loops'),
    ('Unavailable challenge syntax: Delete', 'disallowed-delete: construct a fresh result instead of del'),
    ('Define only solve(data);', 'invalid-entrypoint: define only solve(data), with no imports or helper functions'),
    ('Private/runtime names are unavailable', 'private-name: use ordinary local names and permitted operations'),
    ('Unavailable call: ', 'disallowed-call: use only the listed builtins and data methods'),
    ('Unavailable data method/attribute: ', 'disallowed-method: use only the listed data methods'),
    ('Unavailable challenge syntax: ', 'disallowed-syntax: use loops, conditions and the allowed expressions'),
)


def safe_rejection(tool):
    if tool['name'] != 'write_solution':
        return 'tool-policy-or-validation-rejection'
    error = tool.get('error')
    if not isinstance(error, str):
        return 'tool-policy-or-validation-rejection'
    return next((label for prefix, label in WRITE_REJECTIONS if error.startswith(prefix)),
                'tool-policy-or-validation-rejection')


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
            row['error'] = safe_rejection(tool)
        elif name == 'run_tests':
            row['result'] = json.dumps(counts(json.loads(tool['result'])), sort_keys=True)
        records.append(row)
    return feedback, records
