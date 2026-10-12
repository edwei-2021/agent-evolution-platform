#!/usr/bin/env python3
"""Explicit validation/final S0/S1 runs; completed attempts resume without model replay."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_m_repair import run
from platform_m.dataset import built_in, compare
from platform_m.evidence import Artifacts, atomic_write, canonical, digest
from platform_m.store import Store
from platform_m.gates import source_snapshot
from platform_m.evaluator import image_id
from ollama_bridge import OllamaBridge
from repair_engine import provenance
from repair_fixture import SKILL

ROOT = Path(__file__).resolve().parents[1]

def main(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',args.experiment):
        raise ValueError('Safe experiment ID required')
    if not 1 <= args.repetitions <= 10 or not 2 <= args.calls <= 12 or not 60 <= args.seconds <= 7200:
        raise ValueError('Invalid repetition/call/task deadline')
    artifacts = Artifacts(ROOT/'.local/m/artifacts')
    store = Store(ROOT/'.local/m/control.sqlite3')
    ds = built_in(artifacts)
    tasks = artifacts.get(ds)['tasks']
    final = [t for t in tasks if t['split']=='independent_test']
    validation = [t for t in tasks if t['split']=='validation']
    executions = 2*(len(validation)+len(final)*args.repetitions)
    if args.model_call_budget < executions*args.calls:
        raise ValueError(f'Budget must reserve {executions*args.calls} worst-case model calls before dispatch')
    bodies = {'baseline':args.baseline_body.read_text() if args.baseline_body else SKILL['body'],
              'candidate':args.candidate_body.read_text()}
    if bodies['baseline']==bodies['candidate']:
        raise ValueError('Candidate must differ from baseline')
    for body in bodies.values():
        if not body.strip() or len(body.encode())>8000:
            raise ValueError('Invalid Skill body')
    image = image_id(args.image)
    provider = OllamaBridge(ROOT).state()
    frozen = {'dataset':ds,'bodies':{k:digest(v) for k,v in bodies.items()},'image':image,
              'provider':provider,'code':provenance(),'m_source_hash':source_snapshot(ROOT)[0],
              'calls':args.calls,'seconds':args.seconds,
              'repetitions':args.repetitions,'model_call_budget':args.model_call_budget}
    directory = ROOT/'.local/m/experiments'/args.experiment
    directory.mkdir(parents=True,exist_ok=True)
    config_path = directory/'frozen.json'
    if config_path.exists() and json.loads(config_path.read_text())!=frozen:
        raise ValueError('Resume snapshot changed; start a new experiment')
    atomic_write(config_path,canonical(frozen))
    lock = (ROOT/'.local/runtime.lock').open('a+')
    fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    started = time.time()
    values = []
    schedule = [(t,rep) for t in validation for rep in [0]]+[(t,rep) for t in final for rep in range(args.repetitions)]
    for position,(task,rep) in enumerate(schedule):
        # Balance which Skill runs first across tasks/repetitions.
        order = ('baseline','candidate') if position%2==0 else ('candidate','baseline')
        for label in order:
            if args.max_seconds-(time.time()-started) < args.seconds:
                raise RuntimeError('Whole comparison deadline reached; completed results retained')
            store.event(args.experiment,'task.started',{'task_id':task['id'],'label':label,'repetition':rep})
            result = run(ROOT,task['id'],bodies[label],label,rep,image,args.calls,
                         args.seconds,args.experiment)
            values.append(result['evaluation'])
            if values[-1]['verdict']=='invalid_evaluation':
                raise RuntimeError('Invalid evaluation blocks dependent tasks')
            atomic_write(directory/'progress.json',canonical({'completed':len(values),'total':executions,
                         'elapsed_seconds':time.time()-started,'last':{'task':task['id'],'label':label},'state':'running'}))
            print(f'completed={len(values)}/{executions} task={task["id"]} label={label}',flush=True)
    report = compare([v for v in values if v['split']=='independent_test'],artifacts.get(ds),args.repetitions)
    score = {label:sum(v['score'] for v in values if v['split']=='validation' and v['label']==label)
             for label in bodies}
    report['validation_totals']=score
    report['eligible']=report['eligible'] and score['candidate']>score['baseline']
    report['result_ids']=[v['id'] for v in values]
    report['source_experiment']=args.experiment
    identifier=artifacts.put(report)
    atomic_write(directory/'comparison.json',canonical(report))
    atomic_write(directory/'progress.json',canonical({'completed':executions,'total':executions,
        'state':'completed','eligible':report['eligible'],'report_hash':identifier}))
    store.event(args.experiment,'comparison.completed',{'eligible':report['eligible'],'report_hash':identifier})
    print(json.dumps({'report_hash':identifier,'eligible':report['eligible'],'directory':str(directory)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate-body',type=Path,required=True)
    parser.add_argument('--baseline-body',type=Path)
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--image',default='aep-evaluator:m')
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--calls',type=int,default=6)
    parser.add_argument('--seconds',type=int,default=900)
    parser.add_argument('--max-seconds',type=int,default=14400)
    parser.add_argument('--model-call-budget',type=int,default=840)
    args=parser.parse_args()
    try:
        main(args)
    except Exception as exc:
        print('DBG-M-005 comparison blocked: '+str(exc)+'; inspect .local/m/experiments and task support evidence.',file=sys.stderr)
        raise SystemExit(1)
