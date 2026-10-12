#!/usr/bin/env python3
"""One SDK subprocess using the existing bounded tools and a frozen named Skill."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repair_sdk import run_sdk
from repair_engine import RepairRunner, provenance
from repair_fixture import SKILL
from skill_engine import write

def main(directory):
    cfg = json.loads((directory/'repair-config.json').read_text())
    if cfg.get('canonicalSourceHash'):
        from platform_m.gates import source_snapshot
        if source_snapshot(Path(__file__).resolve().parents[1])[0] != cfg['canonicalSourceHash']:
            raise ValueError('Canonical runner source changed after freezing')
    if cfg['provenance'] != provenance() or cfg['skill']['name'] != SKILL['name']:
        raise ValueError('SDK code or required named Skill changed')
    body = cfg['skill']['body']
    if not body.strip() or len(body.encode()) > 8000:
        raise ValueError('Invalid required Skill body')
    workspace = directory/'task-workspace'
    workspace.mkdir()
    fixture = cfg['fixture']
    (workspace/'solution.py').write_text(fixture['baseline'])
    (directory/'repair-baseline.py').write_text(fixture['baseline'])
    write(directory/'repair-tools.json', [])
    write(directory/'repair-calls.json', [])
    if cfg.get('evaluatorImage'):
        import repair_engine
        from platform_m.evaluator import evaluate
        def container_test(source, split, fixture=None):
            report = evaluate([{'source': source, 'split': split, 'fixture': fixture}], cfg['evaluatorImage'])
            if not report['results'] or not report['cleanup']['removed']:
                raise RuntimeError('Container visible evaluation failed or cleanup unconfirmed')
            return report['results'][0]
        repair_engine.trusted_test = container_test
    asyncio.run(run_sdk(directory, cfg, RepairRunner(directory, cfg)))
    calls = json.loads((directory/'repair-calls.json').read_text())
    initial = '\n'.join(m.get('content', '') or '' for m in calls[0]['request']['messages'])
    if body not in initial or fixture['prompt'] not in initial:
        raise ValueError('Required Skill was not loaded into model request')
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    write(directory/'canonical-sdk.json', {'loaded_skill_hash': digest(cfg['skill']),
          'candidate_source': (directory/'repair-candidate.py').read_text(),
          'calls': len(calls), 'sdk_version': cfg['sdk']['version'], 'stop_reason': 'completed'})

if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
