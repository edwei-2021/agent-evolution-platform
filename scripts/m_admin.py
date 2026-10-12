#!/usr/bin/env python3
"""Local-only manifest administration; reads trusted immutable records, never posts fabricated scores."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_m.store import Store
from platform_m.evidence import Artifacts
from platform_m.releases import Releases
from platform_m.dataset import built_in

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['init-key','dataset','backup-db','register','approve','activate','rollback','active'])
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--hash')
    parser.add_argument('--expected-revision',type=int)
    parser.add_argument('--rationale')
    parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    store=Store(ROOT/'.local/m/control.sqlite3')
    artifacts=Artifacts(ROOT/'.local/m/artifacts')
    releases=Releases(store,artifacts,ROOT/'.local/m/signing.key')
    try:
        if args.action=='init-key':
            releases.init_key()
            value={'key':'created; owner-only .local/m/signing.key'}
        elif args.action=='dataset':
            value={'dataset_hash':built_in(artifacts)}
        elif args.action=='backup-db':
            if not args.destination or args.destination.exists():
                raise ValueError('New backup destination required')
            store.backup(args.destination)
            value={'backup':str(args.destination),'note':'Back up CAS/signing key separately with services stopped'}
        elif args.action=='register':
            if not args.manifest:
                raise ValueError('Complete manifest required')
            value={'hash':releases.register(json.loads(args.manifest.read_text()))}
        elif args.action=='approve':
            if not args.hash or not args.rationale:
                raise ValueError('Manifest hash and rationale required')
            releases.approve(args.hash,'local-owner','approver',args.rationale)
            value={'approved':args.hash}
        elif args.action in ('activate','rollback'):
            if not args.hash or args.expected_revision is None:
                raise ValueError('Manifest hash and expected revision required')
            value=releases.activate(args.hash,args.expected_revision,'local-owner','approver',args.action=='rollback')
        else:
            value=releases.active()
        print(json.dumps(value,indent=2))
    except Exception as exc:
        print('DBG-M-006 release blocked: '+str(exc)+'; inspect manifest/evaluation/key/pointer evidence.',file=sys.stderr)
        raise SystemExit(1)
