"""Fixed supervised GEPA stages; final tasks never enter candidate generation."""
from step_trace import traced
import argparse
import json
from pathlib import Path
from gepa_engine import TASKS, progress, verify
from skill_engine import write

@traced('gepa','role.execute')
def run(role,directory):
    cfg=json.loads((directory/'gepa-config.json').read_text());progress(directory,phase=role)
    if role=='coordinator':
        for name in ('gepa-calls.json','gepa-rollouts.json','gepa-proposals.json'):write(directory/name,[])
        print('Grouped dataset and server-owned model/SDK/tool budgets frozen.',flush=True)
    elif role=='worker':
        from gepa_sdk import search
        search(directory,cfg);print('Real GEPA search completed; validation selection frozen.',flush=True)
    elif role=='reflector':
        selection=json.loads((directory/'gepa-selection.json').read_text())
        s=selection['skill'];(directory/'gepa-selection.md').write_text(f'---\nname: {s["name"]}\ndescription: {s["description"]}\n---\n\n{s["body"]}\n')
        print('Selected Skill exported; no additional reflection or final-data feedback.',flush=True)
    elif role=='evaluator':
        from gepa_sdk import evaluate_final
        evaluate_final(directory,cfg);result=verify(directory);write(directory/'gepa-evaluation.json',result);progress(directory,result=result)
        print('Independent baseline/selected validation and final tasks measured.',flush=True)
    elif role=='reviewer':
        result=verify(directory)
        if result!=json.loads((directory/'gepa-evaluation.json').read_text()):raise ValueError('Stored GEPA result differs from trusted evidence')
        write(directory/'review.json',result);progress(directory,result=result)
        print('Release gate verified: '+str(result['eligible'])+'; activation requires an explicit action.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--role',choices=list(TASKS),required=True);parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();run(args.role,args.run_dir.resolve())
