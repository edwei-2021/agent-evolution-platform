#!/usr/bin/env python3
"""Start the M facade on loopback; legacy GUI/API may run separately on 8765."""
import argparse
import fcntl
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_m.api import create_app, operator_token
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--legacy-port', type=int)
    parser.add_argument('--approver', action='store_true', help='Grant local token approval role explicitly')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = root/'.local/m/service.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    stream = lock.open('a+')
    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    token = operator_token(root)
    app = create_app(root, token, 'approver' if args.approver else 'operator', args.legacy_port)
    print('Local operator token: .local/m/operator.token (not printed). M control port:', args.port)
    uvicorn.run(app, host='127.0.0.1', port=args.port)
