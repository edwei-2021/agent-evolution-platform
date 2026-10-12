#!/usr/bin/env python3
"""Export one redacted gate support report without runtime prompts, tokens or signing keys."""
import argparse
import json
from pathlib import Path
import re
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_m.evidence import canonical, redact

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--check-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'MCHECK-[a-f0-9]{32}',args.check_id):
        parser.error('Use the exact MCHECK ID returned by check_m.py')
    directory=ROOT/'.local/m/support'/args.check_id
    if not directory.is_dir() or directory.is_symlink() or args.output.exists():
        parser.error('Existing check directory and new output filename required')
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['report.json',*[f'M{i}.json' for i in range(1,8)]]:
            path=directory/name
            if path.is_file() and not path.is_symlink():
                archive.writestr(name,canonical(redact(json.loads(path.read_text()))))
    print('Debug support export:',args.output)
