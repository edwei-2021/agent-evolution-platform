"""Runtime-neutral records over the existing bounded runner; no fabricated scores."""
from pathlib import Path
import subprocess
import time
from .contracts import RunResult, Usage, Task
from .evidence import digest, redact

class MockAdapter:
    version = 'deterministic-mock-v1'
    def run(self, task, release, environment, identifier, artifacts):
        task = Task.model_validate(task)
        mode = environment.get('mock_mode', 'succeeded')
        if mode not in ('succeeded', 'failed', 'timed_out', 'cancelled', 'infrastructure_error'):
            raise ValueError('Malformed mock output mode')
        evidence = artifacts.put({'adapter': self.version, 'task_id': task.id, 'mode': mode,
                                  'requested_skill': release['skill_hash']})
        return RunResult(run_id=identifier, task_id=task.id, status=mode,
                         release_snapshot_id=digest(release), environment_snapshot_id=digest(environment),
                         loaded_skill_hash=release['skill_hash'], artifacts=[evidence],
                         output={'mock': True}, error_code=None if mode == 'succeeded' else mode)

class NanobotAdapter:
    version = 'bounded-nanobot-canonical-v1'
    def run(self, task, release, environment, identifier, artifacts, root, directory, config):
        from scripts.repair_runtime import sdk_status
        task = Task.model_validate(task)
        root, directory = Path(root), Path(directory)
        sdk = sdk_status(root)
        if not sdk['available']:
            raise RuntimeError('DBG-M-002 install pinned nanobot SDK first')
        if digest(config['skill']) != release['skill_hash'] or config['taskId'] != task.id:
            raise ValueError('Requested Skill/task snapshot mismatch')
        directory.mkdir(parents=True, exist_ok=False)
        from .evidence import atomic_write, canonical
        config_path = directory/'repair-config.json'
        atomic_write(config_path, canonical(config))
        started = time.monotonic()
        try:
            result = subprocess.run([sdk['python'], str(root/'scripts/m_nanobot_worker.py'), str(directory)],
                                    capture_output=True, text=True, timeout=config['maxSeconds'])
            if result.returncode:
                status = 'infrastructure_error'
                output = {'error': 'SDK execution did not produce trusted evidence', 'exit_code':result.returncode,
                          'stderr':redact(result.stderr[-8000:]), 'stdout':redact(result.stdout[-4000:])}
            else:
                import json
                output = json.loads((directory/'canonical-sdk.json').read_text())
                if output['loaded_skill_hash'] != release['skill_hash']:
                    raise ValueError('Observed Skill hash mismatch')
                status = 'succeeded'
        except subprocess.TimeoutExpired:
            status, output = 'timed_out', {'error': 'SDK task deadline reached'}
        evidence = artifacts.put({'adapter': self.version, 'status': status, 'output': output,
                                  'task_id': task.id, 'config_hash': digest(config)})
        return RunResult(run_id=identifier, task_id=task.id, status=status,
                         release_snapshot_id=digest(release), environment_snapshot_id=digest(environment),
                         loaded_skill_hash=release['skill_hash'], artifacts=[evidence], output=output,
                         usage=Usage(wall_time_ms=(time.monotonic()-started)*1000))
