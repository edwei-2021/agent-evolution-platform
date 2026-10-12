#!/usr/bin/env python3
"""Acceptance executes M1..M7 in dependency order; components never certify phase completion."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_m.gates import Gates, plans, execute

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=['acceptance','components'], default='acceptance')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.profile == 'components':
        import os
        code, output = execute([sys.executable,'-m','pytest','tests_m','-q'], root, os.environ)
        print(output)
        print('COMPONENT CHECK ONLY: Docker and actual SDK/production integration are not certified.')
        raise SystemExit(code)
    result = Gates(root).run(plans(root, sys.executable), {'M_REQUIRE_DOCKER':'1'})
    raise SystemExit(0 if result['status'] == 'passed' else 1)
