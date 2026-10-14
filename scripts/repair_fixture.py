"""Frozen, bounded integer-clamp repair fixture; hidden cases stay outside tools."""
import ast
import hashlib
import json

TASK_ID = 'integer-clamp-v1'
BASELINE = 'def clamp(value, lower, upper):\n    return value\n'
SKILL = {'name': 'python-fix-and-verify', 'description': 'Repair a bounded Python function and verify visible tests.',
         'body': 'Read solution.py, inspect the failure, make the smallest correct repair, run visible tests, and summarize the change. Preserve the clamp(value, lower, upper) signature. Use only granted tools; final claims are not test evidence.'}
PROMPT = 'Repair solution.py. clamp(value, lower, upper) must return value bounded inclusively by lower and upper for integer inputs. If lower > upper, raise ValueError. Preserve the signature. You can read_solution, write_solution and run_tests. Only solution.py may be changed. Imports, attributes, loops, comprehensions and arbitrary commands are unavailable. Hidden tests will be run independently after your turn ends.'
VISIBLE = [([5,0,10],5), ([-1,0,10],0), ([11,0,10],10), ([0,0,10],0), ([10,0,10],10), ([3,4,2],'ValueError')]
HIDDEN = [([-9,-5,-1],-5), ([2,-5,-1],-1), ([-3,-5,-1],-3), ([100,7,7],7), ([-100,-8,-8],-8), ([0,1,-1],'ValueError')]
TOOLS = ('read_solution','write_solution','run_tests')

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_source(source):
    if not isinstance(source,str) or not source.strip() or len(source.encode())>8000: raise ValueError('Solution must be nonempty and at most 8 KB')
    tree=ast.parse(source)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef): raise ValueError('Define only clamp(value, lower, upper)')
    fn=tree.body[0];args=fn.args
    if fn.name!='clamp' or fn.decorator_list or fn.returns or args.defaults or args.kw_defaults or args.vararg or args.kwarg or args.posonlyargs or args.kwonlyargs or [a.arg for a in args.args]!=['value','lower','upper'] or any(a.annotation for a in args.args): raise ValueError('Preserve the exact clamp signature')
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.If,ast.Raise,ast.Assign,ast.Expr,ast.Name,ast.Load,ast.Store,ast.Constant,ast.Call,ast.Compare,ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq,ast.BoolOp,ast.And,ast.Or,ast.UnaryOp,ast.USub,ast.UAdd,ast.Not,ast.BinOp,ast.Add,ast.Sub,ast.IfExp)
    nodes=list(ast.walk(tree))
    if len(nodes)>400: raise ValueError('Solution AST exceeds 400 nodes')
    if sum(isinstance(n,ast.FunctionDef) for n in nodes)!=1: raise ValueError('Nested functions are unavailable')
    for n in nodes:
        if not isinstance(n,allowed): raise ValueError('Unsupported Python syntax: '+type(n).__name__)
        if isinstance(n,ast.Name):
            if not n.id.isidentifier() or n.id.startswith('_') or len(n.id)>30: raise ValueError('Unsupported variable name')
            if isinstance(n.ctx,ast.Store) and n.id in ('min','max','ValueError'): raise ValueError('Cannot replace trusted builtins')
        if isinstance(n,ast.Constant) and not (type(n.value) is int and abs(n.value)<=1000000 or type(n.value) is str and len(n.value)<=200 or n.value is None): raise ValueError('Unsupported constant')
        if isinstance(n,ast.Call) and (not isinstance(n.func,ast.Name) or n.func.id not in ('min','max','ValueError') or n.keywords or len(n.args)>3): raise ValueError('Only min, max and ValueError calls are permitted')
        if isinstance(n,ast.Raise):
            # Python accepts both the trusted exception class and an instance.
            # Keep every other exception, bare re-raise and explicit cause out.
            target=n.exc.func if isinstance(n.exc,ast.Call) else n.exc
            if n.cause is not None or not isinstance(target,ast.Name) or target.id!='ValueError':
                raise ValueError('Only raise ValueError or raise ValueError(...) is permitted; exception chaining is unavailable')
        if isinstance(n,ast.Assign) and any(not isinstance(t,ast.Name) for t in n.targets): raise ValueError('Assign only local variables')
    return tree
