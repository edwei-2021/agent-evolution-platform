#!/usr/bin/env python3
"""Check a Windows Ollama server from WSL. Standard-library-only HTTP client."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.error
import urllib.request


def gateway():
    kernel = Path('/proc/sys/kernel/osrelease').read_text().lower()
    if 'microsoft' not in kernel:
        raise ValueError('Automatic detection requires WSL. Supply --host for an explicit endpoint.')
    routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default'], text=True))
    for route in routes:
        if route.get('gateway'):
            return route['gateway']
    raise ValueError('No IPv4 default gateway. Inspect ip -4 route show default.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='Explicit Windows IPv4 address; default: WSL NAT gateway')
    parser.add_argument('--port', type=int, default=11435)
    parser.add_argument('--model', help='Exact installed model ID, for example qwen3-coder:30b')
    parser.add_argument('--infer', action='store_true', help='Also make one real chat request; requires --model')
    parser.add_argument('--timeout', type=float, default=600, help='Inference timeout in seconds')
    parser.add_argument('--env-file', default='ollama-wsl.env', help='Export file; written only after all requested checks pass')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.timeout <= 0:
        parser.error('Port must be 1..65535; timeout must be positive.')
    if args.infer and not args.model:
        parser.error('--infer requires --model.')
    host = str(ipaddress.IPv4Address(args.host or gateway()))
    base = f'http://{host}:{args.port}'
    # Bypass proxy environment variables for this direct host connection.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'})
        with opener.open(req, timeout=args.timeout if payload is not None else 10) as response:
            return json.load(response)

    print(f'Endpoint: {base}')
    version = request('/api/version')
    if not isinstance(version, dict) or not isinstance(version.get('version'), str):
        raise ValueError('/api/version is not an Ollama version response.')
    print(f"PASS native API; server version: {version['version']}")
    tags = request('/api/tags')
    models = request('/v1/models')
    if not isinstance(tags, dict) or not isinstance(tags.get('models'), list):
        raise ValueError('/api/tags has no model list.')
    if not isinstance(models, dict) or not isinstance(models.get('data'), list):
        raise ValueError('/v1/models has no model list.')
    if not all(isinstance(entry, dict) for entry in tags['models'] + models['data']):
        raise ValueError('Model listings contain invalid entries.')
    ids = [entry['id'] for entry in models.get('data', [])]
    native_ids = [entry.get('name', entry.get('model')) for entry in tags.get('models', [])]
    print('PASS model listing: ' + (', '.join(ids) or '(no models installed)'))
    if args.model and (args.model not in ids or args.model not in native_ids):
        raise ValueError(f'Model {args.model!r} is not listed by both APIs. Pull it on Windows or use the exact listed ID.')
    if args.infer:
        reply = request('/v1/chat/completions', {
            'model': args.model, 'stream': False,
            'messages': [{'role': 'user', 'content': 'Reply with the word OK.'}],
            'max_tokens': 64, 'temperature': 0,
        })
        message = reply['choices'][0]['message']
        if not message.get('content'):
            raise ValueError('Chat response has no visible content. Inspect model behavior/token budget.')
        print('PASS inference: ' + str(message['content']).strip())
    values = {
        'OLLAMA_HOST': base,
        'OLLAMA_BASE_URL': base,
        'OPENAI_BASE_URL': base + '/v1',
        'OPENAI_API_KEY': 'ollama',
    }
    if args.model:
        values['OLLAMA_MODEL'] = args.model
    bypass_hosts = ['localhost', '127.0.0.1', host]
    for name in ('NO_PROXY', 'no_proxy'):
        current = [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]
        values[name] = ','.join(dict.fromkeys(current + bypass_hosts))
    target = Path(args.env_file).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = '# Generated Ollama client endpoints; source this file in Bash.\n'
    content += ''.join(f'export {key}={shlex.quote(value)}\n' for key, value in values.items())
    # Atomic replacement so a failed probe never writes partial endpoint settings.
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'PASS export file: {target.resolve()}')
    print('Next: source ' + shlex.quote(str(target)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.CalledProcessError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        print('Check Windows listener, matching port, current WSL IP/firewall rule, and installed model ID.', file=sys.stderr)
        sys.exit(1)
