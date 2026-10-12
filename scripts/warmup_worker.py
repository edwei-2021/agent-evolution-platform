"""One explicit native model preload; parent owns absolute timeout/cancellation."""
import json
from pathlib import Path
import sys
from ollama_bridge import OllamaBridge, atomic_write

def main():
    config_path, result_path = map(Path, sys.argv[1:])
    job = json.loads(config_path.read_text())
    bridge = OllamaBridge(config_path.parents[2])
    try:
        reply = bridge.request(job['endpoint'], '/api/generate', job['config'],
            {'model': job['config']['model'], 'prompt': '', 'stream': False,
             'keep_alive': f'{job["keepAliveMinutes"]}m'})
        if reply.get('done') is not True or not isinstance(reply.get('model'), str) or not reply['model']:
            raise ValueError('Malformed model preload completion')
        result = {'responseModel': reply['model']}
        for key, output in [('load_duration', 'loadDurationMs'), ('total_duration', 'totalDurationMs')]:
            if key in reply:
                if type(reply[key]) is not int or reply[key] < 0: raise ValueError('Invalid preload timing')
                result[output] = round(reply[key] / 1000000, 3)
        atomic_write(result_path, json.dumps(result))
    except Exception as exc:
        atomic_write(result_path, json.dumps({'error': str(exc)})); return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
