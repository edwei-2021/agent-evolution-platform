"""Isolated trusted evaluator for the accepted pure-function AST subset."""
import json
import resource
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from repair_fixture import VISIBLE, HIDDEN, validate_source

def evaluate(source, split, fixture=None):
    tree=validate_source(source)
    namespace={'__builtins__':{'min':min,'max':max,'ValueError':ValueError}}
    exec(compile(tree,'solution.py','exec'),namespace)
    rows=fixture[split] if fixture is not None else VISIBLE if split=='visible' else HIDDEN
    records=[]
    for inputs,expected in rows:
        try:
            value=namespace['clamp'](*inputs)
            actual=value if type(value) in (int,str) else '<non-integer result>'
            passed=type(value) is int and type(expected) is int and value==expected
        except Exception as exc:
            actual=type(exc).__name__;passed=type(exc) is ValueError and expected=='ValueError'
        records.append({'inputs':inputs,'expected':expected,'actual':actual,'passed':passed})
    return {'split':split,'passed':sum(r['passed'] for r in records),'total':len(rows),'records':records}

def main():
    resource.setrlimit(resource.RLIMIT_CPU,(2,2));resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    try:
        raw=sys.stdin.read(1000001)
        if len(raw)>1000000:raise ValueError('Evaluator input exceeds size limit')
        data=json.loads(raw)
        jobs=data.get('jobs',[data])
        if not isinstance(jobs,list) or not 1<=len(jobs)<=32:raise ValueError('Use 1..32 trusted evaluation jobs')
        results=[]
        for job in jobs:
            if not isinstance(job,dict) or set(job)-{'source','split','fixture'} or job.get('split') not in ('visible','hidden'):raise ValueError('Unknown evaluation job/split')
            results.append(evaluate(job['source'],job['split'],job.get('fixture')))
        result={'results':results} if 'jobs' in data else results[0]
    except Exception as exc: result={'error':str(exc)}
    print(json.dumps(result,ensure_ascii=False))
    return int('error' in result)

if __name__=='__main__':raise SystemExit(main())
