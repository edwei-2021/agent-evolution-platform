"""Five supervised stages around one bounded nanobot SDK repair worker."""
from step_trace import traced
import argparse
import asyncio
import difflib
import json
from pathlib import Path
from repair_fixture import BASELINE, SKILL, PROMPT
from repair_engine import TASKS, provenance, progress, trusted_test, verify
from skill_engine import write

@traced('nanobot','role.execute')
def run_role(role,directory):
    cfg=json.loads((directory/'repair-config.json').read_text())
    if cfg['provenance']!=provenance():raise ValueError('Frozen repair provenance changed')
    progress(directory,phase=role)
    if role=='coordinator':
        workspace=directory/'task-workspace';workspace.mkdir()
        (workspace/'solution.py').write_text(BASELINE)
        (workspace/'AGENTS.md').write_text('Work only on solution.py using the three granted tools. No user config, shell, network tools or shared memory.\n')
        (directory/'repair-baseline.py').write_text(BASELINE)
        write(directory/'repair-tools.json',[]);write(directory/'repair-calls.json',[])
        write(directory/'repair-baseline-evaluation.json',trusted_test(BASELINE,'visible'))
        print('Fresh workspace prepared; baseline visible tests measured. Hidden tests withheld.',flush=True)
    elif role=='worker':
        from repair_sdk import run_sdk
        asyncio.run(run_sdk(directory,cfg));print('Real nanobot SDK turn finished; candidate frozen for trusted evaluation.',flush=True)
    elif role=='reflector':
        tools=json.loads((directory/'repair-tools.json').read_text())
        report={'toolCalls':len(tools),'failedTools':sum(t['status']=='failed' for t in tools),'modelReflection':False,
                'note':'Trace summary only; fixed Skill and no GEPA search or extra model call.'}
        write(directory/'repair-reflection.json',report);print('Tool evidence summarized; no new model request.',flush=True)
    elif role=='evaluator':
        result=verify(directory);write(directory/'repair-evaluation.json',result)
        candidate=(directory/'repair-candidate.py').read_bytes().decode('utf-8')
        patch=''.join(difflib.unified_diff(BASELINE.splitlines(keepends=True),candidate.splitlines(keepends=True),fromfile='a/solution.py',tofile='b/solution.py'))
        (directory/'repair-change.patch').write_text(patch)
        progress(directory,result=result);print('Independent visible and hidden tests measured: '+str(result['repairPassed']),flush=True)
    elif role=='reviewer':
        result=verify(directory)
        if result!=json.loads((directory/'repair-evaluation.json').read_text()):raise ValueError('Stored repair result differs from trusted evidence')
        write(directory/'review.json',result);progress(directory,result=result)
        print('Repair evidence verified. No source repository changes or automatic Skill activation.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--role',choices=list(TASKS),required=True);parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();run_role(args.role,args.run_dir.resolve())
