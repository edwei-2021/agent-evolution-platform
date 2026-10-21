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
    def run(self, task, release, environment, identifier, artifacts, root, directory, config, *, cancelled=None, heartbeat=None):
        from scripts.repair_runtime import sdk_status
        task = Task.model_validate(task)
        root, directory = Path(root), Path(directory)
        source_root=Path(config.get('sourceRoot',root))
        sdk = sdk_status(source_root)
        if not sdk['available']:
            import json
            raise RuntimeError('DBG-M-002 SDK probe failed: '+json.dumps(sdk, ensure_ascii=False))
        if digest(config['skill']) != release['skill_hash'] or config['taskId'] != task.id:
            raise ValueError('Requested Skill/task snapshot mismatch')
        directory.mkdir(parents=True, exist_ok=False)
        from .evidence import atomic_write, canonical
        config_path = directory/'repair-config.json'
        atomic_write(config_path, canonical(config))
        started = time.monotonic()
        try:
            from .process import execute
            source_root=Path(config.get('sourceRoot',root))
            result = execute([sdk['python'], str(source_root/'scripts/m_nanobot_worker.py'), str(directory)],
                             directory,config['maxSeconds'],config['deadlineEpoch'],cancelled=cancelled,heartbeat=heartbeat)
            if result['state'] in ('cancelled','timed_out'):
                status=result['state'];output={'error':'Native execution stopped under frozen policy','cleanup_confirmed':True}
            elif result['exit_code']:
                status = 'infrastructure_error'
                output = {'error': 'SDK execution did not produce trusted evidence', 'exit_code':result['exit_code'],
                          'stderr':redact(result['stderr']), 'stdout':redact(result['stdout'])}
            else:
                import json
                output = json.loads((directory/'canonical-sdk.json').read_text())
                if output['loaded_skill_hash'] != release['skill_hash']:
                    raise ValueError('Observed Skill hash mismatch')
                status = 'succeeded'
        except subprocess.TimeoutExpired as exc:
            def tail(value, size):
                if isinstance(value, bytes):
                    value = value.decode('utf-8', errors='replace')
                return redact((value or '')[-size:])
            status, output = 'timed_out', {'error': 'SDK task deadline reached',
                'timeout_seconds': config['maxSeconds'], 'elapsed_seconds': time.monotonic()-started,
                'python': sdk['python'], 'stdout': tail(exc.stdout, 4000), 'stderr': tail(exc.stderr, 8000),
                'run_directory': str(directory)}
        evidence = artifacts.put({'adapter': self.version, 'status': status, 'output': output,
                                  'task_id': task.id, 'config_hash': digest(config)})
        return RunResult(run_id=identifier, task_id=task.id, status=status,
                         release_snapshot_id=digest(release), environment_snapshot_id=digest(environment),
                         loaded_skill_hash=release['skill_hash'], artifacts=[evidence], output=output,
                         error_code=None if status=='succeeded' else 'DBG-M-002:'+status,
                         usage=Usage(tool_calls=output.get('toolCalls',0),wall_time_ms=(time.monotonic()-started)*1000))
