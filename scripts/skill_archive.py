"""Bounded, read-only Skill lineage for queries and diagnostic exports."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from debug_log import redact
from skill_audit import conditions, feedback_refs, text_hash

TASKS = {'gepa-evolution': 'gepaConfig', 'llm-evolution': 'llmConfig', 'skill-evolution': 'skillConfig'}
# Remove large task fixtures and volatile UI details inside SQLite before decoding.
THIN = "json_remove(data,'$.gepaConfig.datasetSnapshot.data','$.agents','$.events','$.artifacts','$.gepaProgress','$.llmProgress','$.skillProgress')"


def connect(root):
    root = Path(root)
    if (root/'.local').is_symlink():
        raise ValueError('Local storage cannot be a symlink')
    path = root/'.local/runtime.sqlite3'
    if path.is_symlink():
        raise ValueError('Runtime database cannot be a symlink')
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.5)


def index(root, offset=0, task='', limit=20):
    if type(offset) is not int or not 0 <= offset <= 100000 or task not in ('', *TASKS) or not 1 <= limit <= 1000:
        raise ValueError('Invalid Skill history query')
    with connect(root) as db:
        where = "json_extract(data,'$.task') IN ('gepa-evolution','llm-evolution','skill-evolution')"
        args = []
        if task:
            where += " AND json_extract(data,'$.task')=?"
            args.append(task)
        total = db.execute('SELECT COUNT(*) FROM runs WHERE '+where, args).fetchone()[0]
        rows = db.execute("SELECT id,json_extract(data,'$.task'),json_extract(data,'$.status'),created FROM runs WHERE "+where+
                          ' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
    return {'schemaVersion': 1, 'offset': offset, 'limit': limit, 'total': total,
            'runs': [dict(zip(('id', 'task', 'status', 'createdAt'), row)) for row in rows], 'historyOnly': True}


def candidate(body, base):
    value = {key: base.get(key) for key in ('name', 'description')} | {'body': body}
    if all(isinstance(v, str) for v in value.values()):
        value['hash'] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return value


def instruction(skill):
    if not isinstance(skill, dict):
        return {'text': None, 'hash': None, 'bodyHash': None, 'redacted': False}
    body = skill.get('body')
    if not isinstance(body, str) or len(body.encode()) > 16000:
        body = None
    cleaned = redact(body) if body is not None else None
    return {'text': cleaned, 'hash': skill.get('hash'), 'bodyHash': text_hash(body) if body is not None else skill.get('bodyHash'),
            'redacted': cleaned != body, 'exportedBodyHash': text_hash(cleaned) if cleaned is not None else None}


def clean_conditions(value):
    if not isinstance(value, dict):
        return {}
    text_keys = ('component','profile','baselineVersionId','datasetVersion','datasetHash','model','provider','reasoningEffort','trigger','mutation','sdkVersion','optimizerVersion','reflectionInstruction')
    number_keys = ('outputLimit','temperature','seed','reflectionBatch','metricEvaluations','callsUsed','round','bankRevision')
    result = {k: redact(value[k])[:1000] for k in text_keys if isinstance(value.get(k),str)}
    result.update({k:value[k] for k in number_keys if type(value.get(k)) in (int,float)})
    for key in ('chosenForNext','skipPerfectScore','cacheEvaluation','useMerge'):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    result['limits'] = {k:v for k,v in value.get('limits',{}).items() if k in
        ('metricBudget','proposalBudget','taskCallBudget','callBudget','maxSeconds','callTimeoutSeconds','maxCandidates') and type(v) is int}
    result['codeHashes'] = {k:v for k,v in value.get('codeHashes',{}).items()
                           if re.fullmatch(r'[a-z_]+\.py',k) and isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v)}
    return result


def clean_search(value):
    if not isinstance(value, dict):
        return None
    skipped = []
    for e in value.get('skipped',[])[:80]:
        if not isinstance(e,dict):
            continue
        skipped.append({'iteration':e.get('iteration') if type(e.get('iteration')) is int else None,
                        'candidate_idx':e.get('candidate_idx') if type(e.get('candidate_idx')) is int else None,
                        'reason':e.get('reason') if e.get('reason') in ('all_scores_perfect','no_trajectories') else 'unknown',
                        'scores':[v for v in (e.get('scores') or [])[:50] if type(v) in (int,float) and 0<=v<=1]})
    raw = value.get('stop')
    stop = None
    if isinstance(raw,dict):
        stop={k:raw.get(k) for k in ('used','metricBudget','requiredNext','proposals') if type(raw.get(k)) is int}
        stop['reasons']=[r for r in raw.get('reasons',[]) if r in ('proposal-failed','iteration-reservation','proposal-budget','deadline')]
        stop['at']=str(raw.get('at',''))[:40]
    return {'seed':value.get('seed') if type(value.get('seed')) is int else None,'skipped':skipped,'stop':stop}


def recover_response(reader, filename, base, config, component):
    calls=reader.json(filename,[],2*1024*1024)
    if not isinstance(calls,list) or len(calls)>200:
        return None
    for call in reversed(calls):
        if not isinstance(call,dict) or component=='llm-reflector' and call.get('kind')!='reflection':
            continue
        try:
            answer=json.loads(call['response']['choices'][0]['message']['content'])
            body=answer.get('skill_body' if component=='gepa-worker' else 'body')
            if not isinstance(body,str):
                continue
            context=json.loads(call['request']['messages'][1]['content'])
            parent_body=context.get('candidate',{}).get('skill_body',base.get('body'))
            references=feedback_refs(context.get('training',context.get('trainingFailures',[])))
            return {'candidate':dict(candidate(body,base),bodyHash=text_hash(body)),
                    'parent':candidate(parent_body,base),'status':'returned','origin':'recovered-response',
                    'startedAt':call.get('startedAt'),'finishedAt':call.get('finishedAt'),
                    'trainingRefs':references,'conditions':conditions(config,component)}
        except (ValueError,TypeError,KeyError,IndexError,AttributeError):
            continue
    return None


def snapshot(root, run_id, *, run=None, input_budget=8*1024*1024):
    from change_trace import Reader
    if not re.fullmatch(r'RUN-[A-Za-z0-9-]+', run_id):
        raise ValueError('Invalid Skill Run identity')
    if run is None:
        with connect(root) as db:
            row = db.execute('SELECT '+THIN+' FROM runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise KeyError('Run not found')
        if len(row[0].encode()) > 1000000:
            raise ValueError('Run metadata exceeds its preview bound')
        run = json.loads(row[0])
    task = run.get('task')
    if task not in TASKS:
        raise ValueError('Run does not generate Skills')
    directory = Path(root)/'.local/runs'/run_id
    if directory.parent.is_symlink():
        raise ValueError('Run storage cannot be a symlink')
    reader = Reader(directory, maximum=min(8*1024*1024, max(0, input_budget)))
    cfg = run.get(TASKS[task], {})
    base = cfg.get('baseline', {}).get('skill', {})
    component = {'gepa-evolution': 'gepa-worker', 'llm-evolution': 'llm-reflector', 'skill-evolution': 'rule-worker'}[task]
    entries = {}
    selection = None
    validation = {}
    if task == 'gepa-evolution':
        proposals = reader.json('gepa-proposals.json', [])
        search = reader.json('gepa-search.json', {})
        selected = reader.json('gepa-selection.json', {})
        selection = selected.get('skill', {}).get('body')
        for i, item in enumerate(search.get('candidates', [])):
            scores = search.get('validationScores', [])
            if i < len(scores):
                validation[item.get('skill_body', '')] = scores[i]
        if not isinstance(proposals, list) or len(proposals) > 8:
            raise ValueError('Invalid bounded Skill proposals')
        for p in proposals:
            entries[p['id']] = {'candidate': candidate(p.get('body'), base), 'parent': candidate(p.get('parentBody'), base),
                                'trainingRefs': feedback_refs(p.get('training', [])), 'startedAt': None,
                                'finishedAt': p.get('createdAt'), 'status': 'generated',
                                'conditions': conditions(cfg,component) | {'seed':search.get('seed')}}
    elif task == 'llm-evolution':
        search = reader.json('llm-search.json', {})
        evaluation = reader.json('llm-evaluation.json', {})
        if search.get('candidate'):
            entries['C1'] = {'candidate': search['candidate'], 'parent': base, 'status': 'generated'}
        if evaluation.get('selectedId'):
            selection = base.get('body') if evaluation['selectedId'] == 'C0' else search.get('candidate', {}).get('body')
    else:
        search = reader.json('search.json', {})
        probes = reader.json('training-probes.json', [])
        if len(probes) > 4:
            raise ValueError('Invalid rule probe history')
        parent = base
        for i, probe in enumerate(probes):
            if len(probe.get('trials', [])) > 4:
                raise ValueError('Invalid bounded rule trials')
            for j, trial in enumerate(probe.get('trials', [])):
                entries[f'T{i+1:02d}{j+1:02d}'] = {'candidate': trial.get('skill'), 'parent': parent, 'status': 'generated',
                    'conditions': conditions(cfg, component) | {'mutation': trial.get('rule'), 'round': i+1}}
            candidates = search.get('candidates', [])
            if i+1 < len(candidates):
                parent = candidates[i+1]['skill']
        # Interrupted legacy rules may have only a saved progress candidate list.
        if not probes:
            state = reader.json('progress.json', search)
            for c in state.get('candidates', search.get('candidates', []))[1:5]:
                entries[c['id']] = {'candidate': c.get('skill'), 'parent': parent, 'status': 'generated'}
                parent = c.get('skill', {})
        result = run.get('skillResult', {})
        selection = result.get('selectedSkill', {}).get('body')
    audit_dir = directory/'skill-audit'
    if audit_dir.is_symlink():
        raise ValueError('Skill audit storage cannot be a symlink')
    if audit_dir.is_dir():
        for number, path in enumerate(sorted(audit_dir.iterdir())):
            if number >= 32:
                raise ValueError('Skill audit exceeds 32 attempts')
            if not re.fullmatch(r'(P\d{3}|C\d{1,2}|T\d{4})\.json', path.name):
                continue
            audit = reader.json('skill-audit/'+path.name, {}, 128000)
            if audit and audit.get('id') == path.stem:
                existing = entries.get(path.stem)
                # Authoritative candidate bodies win; keep an explicit mismatch warning.
                if existing and instruction(existing.get('candidate'))['bodyHash'] != instruction(audit.get('candidate'))['bodyHash']:
                    reader.warn('skill-audit/'+path.name+': candidate identity differs; using saved proposal')
                    existing['auditMismatch'] = True
                else:
                    entries[path.stem] = {**(existing or {}), **audit, 'origin': 'recorded'}
    # A process may stop after the response was persisted but before the proposal
    # ledger/audit update. Recover only the bounded instruction field, never the
    # raw request, training source, expected answers or complete model response.
    recoveries = []
    if task == 'gepa-evolution':
        folder=directory/'reflections'
        if folder.is_symlink():
            raise ValueError('Reflection storage cannot be a symlink')
        if folder.is_dir():
            for number, path in enumerate(sorted(folder.iterdir())):
                if number>=16:
                    raise ValueError('Too many reflection directories')
                if re.fullmatch(r'P\d{3}',path.name):
                    recoveries.append((path.name,'reflections/'+path.name+'/repair-calls.json'))
    elif task == 'llm-evolution':
        recoveries=[('C1','llm-calls.json')]
    for identifier, filename in recoveries:
        if instruction(entries.get(identifier,{}).get('candidate'))['text'] is None:
            recovered=recover_response(reader,filename,base,cfg,component)
            if recovered:
                entries[identifier]={**recovered,**entries.get(identifier,{})}
                if instruction(entries[identifier].get('candidate'))['text'] is None:
                    entries[identifier]['candidate']=recovered['candidate']
                    entries[identifier]['origin']='recovered-response'
    rows = []
    for identifier, entry in sorted(entries.items()):
        item, parent = instruction(entry.get('candidate')), instruction(entry.get('parent', base))
        before, after = parent['text'], item['text']
        rows.append({'id': identifier, 'status': entry.get('status', 'unknown'),
                     'origin': entry.get('origin', 'reconstructed'),
                     'startedAt': entry.get('startedAt'), 'finishedAt': entry.get('finishedAt'),
                     'instruction': item, 'parent': parent,
                     'changed': before != after if before is not None and after is not None else None,
                     'patch': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='parent', tofile=identifier)) if before is not None and after is not None else None,
                     'conditions': clean_conditions(entry.get('conditions', conditions(cfg, component))),
                     'trainingRefs': feedback_refs(entry.get('trainingRefs', [])), 'errorType': entry.get('errorType'),
                     'matchesSelection': selection == (entry.get('candidate') or {}).get('body') if selection is not None else None,
                     'validationScore': validation.get((entry.get('candidate') or {}).get('body')),
                     'auditMismatch': entry.get('auditMismatch', False)})
    versions = []
    try:
        with connect(root) as db:
            table = {'gepa-evolution': 'gepa_versions', 'llm-evolution': 'llm_versions', 'skill-evolution': 'skill_versions'}[task]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                for raw, in db.execute('SELECT data FROM '+table+' WHERE run_id=? LIMIT 100', (run_id,)):
                    v = json.loads(raw)
                    versions.append({k: v.get(k) for k in ('id', 'label', 'parentId', 'createdAt')} | {'skillHash': v.get('skill', {}).get('hash')})
    except (sqlite3.Error, OSError):
        reader.warn('Approved version database unavailable')
    search_audit = reader.json('gepa-search-audit.json', None, 64000) if task == 'gepa-evolution' else None
    return {'schemaVersion': 1, 'runId': run_id, 'task': task, 'runStatus': run.get('status'),
            'baselineVersionId': cfg.get('baseline', {}).get('id'), 'baseline': instruction(base),
            'conditions': clean_conditions(conditions(cfg, component)), 'records': rows, 'approvedVersions': versions,
            'searchAudit': clean_search(search_audit), 'inputBytes': reader.bytes_read,
            'warnings': reader.warnings, 'historyOnly': True}
