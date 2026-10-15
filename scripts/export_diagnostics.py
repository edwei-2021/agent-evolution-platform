#!/usr/bin/env python3
"""Export bounded local diagnostics without SDK imports or model requests."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from debug_log import safe_details, redact
from diagnostic_log import CATEGORIES, MAX_BYTES, bodyless

MAX_EXPORT = 32 * 1024 * 1024


def status_snapshot(root):
    root = Path(root)
    status = {'observedAt': datetime.now(timezone.utc).isoformat(), 'runs': []}
    database = root/'.local/runtime.sqlite3'
    if database.is_file() and not database.is_symlink():
        try:
            with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5) as db:
                for raw, in db.execute('SELECT data FROM runs ORDER BY created DESC LIMIT 10'):
                    if len(raw)>1000000:continue
                    run = json.loads(raw)
                    summary={k:run.get(k) for k in ('id','status','task','createdAt','updatedAt','error')}
                    config=run.get('repairConfig') or run.get('gepaConfig') or run.get('llmConfig') or {}
                    summary['frozenCodeHashes']=config.get('provenance',{}).get('codeHashes',{})
                    summary['limits']={k:config.get(k) for k in ('callBudget','maxSeconds','callTimeoutSeconds')}
                    status['runs'].append(summary)
        except (OSError,sqlite3.Error,ValueError) as exc:
            status['runtimeReadError'] = str(exc)
    for name in ('warmup.json','settings.json'):
        path = root/'.local/ollama'/name
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536:
            try:
                value = json.loads(path.read_text())
                status[name] = ({k:value.get(k) for k in
                    ('id','status','phase','startedAt','finishedAt','error','endpoint','revision',
                     'timeoutSeconds','elapsedMs','keepAliveMinutes','responseModel','transport')}
                    if name=='warmup.json' else value)
            except (OSError,ValueError) as exc:
                status[name] = {'readError':str(exc)}
    return bodyless(safe_details(status))


def build_bundle(root=ROOT):
    root = Path(root).resolve()
    data = io.BytesIO()
    total = 0
    omissions = []
    with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        folder = root/'.local/diagnostics'
        if folder.is_dir() and not folder.is_symlink():
            for path in sorted(folder.iterdir()):
                if not path.is_file() or path.is_symlink():continue
                if not any(path.name==c+'.jsonl' or path.name in (c+'.jsonl.1',c+'.jsonl.2') for c in CATEGORIES):continue
                # A collector may race append/rotation. Read once and redact again.
                try:
                    size=path.stat().st_size
                    if size>MAX_BYTES or total+size>MAX_EXPORT:
                        omissions.append({'file':path.name,'reason':'export_size_limit'})
                        continue
                    with path.open('rb') as stream:raw=stream.read(MAX_BYTES)
                except OSError as exc:
                    omissions.append({'file':path.name,'reason':str(exc)})
                    continue
                lines=[]
                for line in raw.decode(errors='replace').splitlines():
                    try:lines.append(json.dumps(bodyless(safe_details(json.loads(line))),ensure_ascii=False))
                    except ValueError:lines.append(json.dumps({'partialLine':redact(line)[:1000]}))
                bundle.writestr('logs/'+path.name,'\n'.join(lines)+'\n')
                total += len(raw)
        bundle.writestr('status.json',json.dumps(status_snapshot(root),ensure_ascii=False,indent=2))
        source = {}
        for name in ('serve_gui.py','diagnostic_log.py','ollama_bridge.py','warmup_worker.py',
                     'sdk_runtime_probe.py','repair_fixture.py','llm_transport.py'):
            path = root/'scripts'/name
            if path.is_file() and not path.is_symlink():source[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            commit = subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=2).stdout.strip()
        except (OSError,subprocess.TimeoutExpired):commit=None
        bundle.writestr('source.json',json.dumps({'revisionOnDisk':commit,'hashesOnDisk':source},indent=2))
        bundle.writestr('manifest.json',json.dumps({'schemaVersion':1,'inputBytes':total,'omitted':omissions,
            'contains':'bounded categorized metadata logs and status; no raw prompts, model responses or task source',
            'networkRequests':0},indent=2))
    return data.getvalue()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    destination=args.output or args.root/'.local/diagnostics'/('diagnostics-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.zip')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(build_bundle(args.root))
    print('DIAGNOSTIC_SUPPORT '+str(destination.resolve()))
    return 0

if __name__=='__main__':raise SystemExit(main())
