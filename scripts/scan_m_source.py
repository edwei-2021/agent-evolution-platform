#!/usr/bin/env python3
"""High-confidence credential patterns over Git source, excluding private runtime state."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PATTERNS=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{36,}',
          r'AKIA[A-Z0-9]{16}',r'sk-proj-[A-Za-z0-9_-]{40,}']

if __name__=='__main__':
    files=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,
                         capture_output=True,text=True,check=True).stdout.splitlines()
    findings=[]
    for name in files:
        path=ROOT/name
        if not path.is_file() or name==Path(__file__).relative_to(ROOT).as_posix():
            continue
        text=path.read_text(errors='replace')
        for line_number,line in enumerate(text.splitlines(),1):
            if any(re.search(pattern,line) for pattern in PATTERNS):
                findings.append({'path':name,'line':line_number})
    if findings:
        print('DBG-M-007 credential pattern found; locations only:',findings,file=sys.stderr)
        raise SystemExit(1)
    print('High-confidence source credential-pattern scan passed (not an exhaustive secret detector).')
