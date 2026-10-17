"""Opt-in pure Python challenge policy; legacy clamp policy remains separate."""
import ast
import copy
import math

POLICY = 'python-challenge-v1'
BUILTINS = {'len': len, 'range': range, 'enumerate': enumerate, 'zip': zip, 'min': min, 'max': max,
            'sum': sum, 'sorted': sorted, 'reversed': reversed, 'abs': abs, 'all': all, 'any': any,
            'set': set, 'list': list, 'dict': dict, 'str': str, 'int': int, 'float': float, 'bool': bool,
            'ValueError': ValueError}
METHODS = {'append', 'extend', 'copy', 'update', 'setdefault', 'pop', 'get', 'items', 'keys', 'values', 'lower', 'upper', 'strip', 'split', 'join',
           'startswith', 'endswith', 'replace', 'count', 'index', 'add', 'discard', 'sort', 'reverse'}


def model_contract():
    return ('Allowed builtins: ' + ', '.join(sorted(BUILTINS)) + '. Allowed data methods: ' +
            ', '.join(sorted(METHODS)) + '. No other calls or methods are available. '
            'Use explicit loops instead of comprehensions or helper functions. Only reverse= is an allowed call keyword. '
            'Numeric literals must be finite with magnitude <=1000000; power (**) is unavailable. '
            'Raise only ValueError or ValueError(...), without chaining. Source <=8 KB and 1000 AST nodes. '
            'Use character membership in a literal string for restricted character checks. Do not repeat a rejected construct; rewrite using this allowlist.')


def validate_source(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 8000:
        raise ValueError('Define solve(data) in at most 8 KB')
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f'Python syntax error at line {exc.lineno}: {exc.msg}') from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('Define only solve(data); imports and module statements are unavailable')
    fn = tree.body[0]
    args = fn.args
    if (fn.name != 'solve' or fn.decorator_list or fn.returns or args.defaults or args.kw_defaults or
            args.vararg or args.kwarg or args.posonlyargs or args.kwonlyargs or
            [a.arg for a in args.args] != ['data'] or any(a.annotation for a in args.args)):
        raise ValueError('Preserve exactly solve(data), without decorators, defaults or annotations')
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If, ast.For, ast.While,
               ast.Break, ast.Continue, ast.Pass, ast.Raise, ast.Assign, ast.AugAssign, ast.Expr,
               ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call, ast.Attribute, ast.keyword,
               ast.Compare, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.In, ast.NotIn,
               ast.Is, ast.IsNot, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.USub, ast.UAdd, ast.Not,
               ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.IfExp,
               ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript, ast.Slice)
    nodes = list(ast.walk(tree))
    if len(nodes) > 1000 or sum(isinstance(n, ast.FunctionDef) for n in nodes) != 1:
        raise ValueError('Nested functions or more than 1000 AST nodes are unavailable')
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError('Unavailable challenge syntax: ' + type(node).__name__)
        if isinstance(node, ast.Name):
            if node.id.startswith('_') or len(node.id) > 40:
                raise ValueError('Private/runtime names are unavailable')
            if isinstance(node.ctx, ast.Store) and node.id in {*BUILTINS, 'solve'}:
                raise ValueError('Cannot replace trusted builtins or the entrypoint')
        if isinstance(node, ast.Attribute) and (node.attr not in METHODS or not isinstance(node.ctx, ast.Load)):
            raise ValueError(f'Unavailable data method/attribute: {node.attr[:40]} at line {node.lineno}. ' + model_contract())
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in BUILTINS or
                    isinstance(node.func, ast.Attribute) and node.func.attr in METHODS):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else type(node.func).__name__
                raise ValueError(f'Unavailable call: {name[:40]} at line {node.lineno}. ' + model_contract())
            if any(k.arg is None or k.arg not in ('reverse',) for k in node.keywords):
                raise ValueError('Only the reverse keyword is available')
        if isinstance(node, ast.Constant):
            value = node.value
            if not (value is None or type(value) is bool or type(value) in (int, float) and
                    abs(value) <= 1000000 and math.isfinite(value) or type(value) is str and len(value) <= 2000):
                raise ValueError(f'Unsupported or oversized constant at line {node.lineno}; use finite numeric literals with magnitude <=1000000 and strings <=2000 characters')
        if isinstance(node, ast.Raise):
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if node.cause is not None or not isinstance(target, ast.Name) or target.id != 'ValueError':
                raise ValueError('Only raise ValueError or ValueError(...) is available; no chaining')
    return tree


def check_json(value, depth=0, counter=None):
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if depth > 8 or counter[0] > 2000:
        raise ValueError('JSON inputs/outputs exceed depth 8 or 2000 nodes')
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float) and abs(value) <= 1000000 and math.isfinite(value):
        return
    if type(value) is str and len(value) <= 2000:
        return
    if type(value) in (list, dict) and len(value) <= 200:
        if type(value) is dict and any(type(k) is not str or len(k) > 100 for k in value):
            raise ValueError('JSON object keys must be short strings')
        for item in value.values() if type(value) is dict else value:
            check_json(item, depth + 1, counter)
        return
    raise ValueError('Use bounded JSON values, finite numbers and lists/objects of at most 200 elements')


def equal(actual, expected, *, tolerant=True):
    if type(actual) in (int, float) and type(expected) in (int, float):
        if not tolerant:
            return type(actual) is type(expected) and actual == expected
        return abs(actual) <= 1000000 and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(equal(a, b, tolerant=tolerant) for a, b in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(equal(actual[k], expected[k], tolerant=tolerant) for k in actual)
    return actual == expected


def evaluate(source, split, fixture):
    tree = validate_source(source)
    records = []
    for case in fixture[split]:
        check_json(case['input'])
        # Reset both namespace and mutable input for every case.
        namespace = {'__builtins__': dict(BUILTINS)}
        exec(compile(tree, 'solution.py', 'exec'), namespace)
        data = copy.deepcopy(case['input'])
        try:
            value = namespace['solve'](data)
        except Exception as exc:
            actual = type(exc).__name__
            passed = type(exc) is ValueError and case.get('raises') == 'ValueError'
        else:
            try:
                check_json(value)
            except ValueError:
                actual, passed = '<unsupported or oversized output>', False
            else:
                actual, passed = value, 'expected' in case and equal(value, case['expected'])
        unchanged = equal(data, case['input'], tolerant=False)
        passed = bool(passed and unchanged)
        records.append({'inputs': [case['input']], 'expected': case.get('expected', case.get('raises')),
                        'actual': actual, 'passed': passed, 'inputUnchanged': unchanged})
    return {'split': split, 'passed': sum(r['passed'] for r in records), 'total': len(records), 'records': records}
