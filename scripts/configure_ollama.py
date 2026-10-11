#!/usr/bin/env python3
"""Save Windows Ollama client settings without any network request."""
import argparse
from pathlib import Path
import sys
from ollama_bridge import OllamaBridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='', help='Windows IPv4; omitted: discover WSL NAT gateway')
    parser.add_argument('--port', type=int, default=11435)
    parser.add_argument('--model', default='', help='Exact model ID; no model is selected automatically')
    parser.add_argument('--metadata-timeout', type=int, default=10)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--max-tokens', type=int, default=256)
    parser.add_argument('--export-env', action='store_true', help='Also write .local/ollama/client.env using the current gateway')
    args = parser.parse_args()
    bridge = OllamaBridge(Path(__file__).resolve().parents[1])
    bridge.save({'host': args.host, 'port': args.port, 'model': args.model,
                 'metadataTimeout': args.metadata_timeout, 'inferenceTimeout': args.timeout,
                 'maxTokens': args.max_tokens}, bridge.state()['revision'])
    print(f'Saved {bridge.path}. No network request or model inference was performed.')
    if args.export_env:
        target = bridge.path.parent / 'client.env'
        bridge.export_environment(target)
        print(f'Client exports: {target}. Source the file in Bash; regenerate after WSL routing changes.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
