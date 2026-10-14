"""Test-only role launcher: pause between real trusted reviewer replays."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import gepa_engine
from gepa_agents import run

directory = Path(sys.argv[1])
delay = float(sys.argv[2])
if not 0 < delay <= 600:
    raise ValueError('Controlled delay must be bounded')
count = len(json.loads((directory/'gepa-rollouts.json').read_text()))
original = gepa_engine.verify_repair

def delayed(*args, **kwargs):
    result = original(*args, **kwargs)
    time.sleep(delay / max(1, count))
    return result

gepa_engine.verify_repair = delayed
print(f'GEPA_CONTROLLED_REVIEW delay_seconds={delay} rollouts={count}', flush=True)
run('reviewer', directory)
