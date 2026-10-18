"""Read-only, bounded projections of persisted source edits and Skill decisions.

Never imports an SDK, executes uploaded code, or recomputes a historical score.
"""
import difflib
import json
import os
from pathlib import Path
import re
import stat
from task_records import catalog, records


def patch(before, after):
    return ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                     fromfile='before', tofile='after'))


class Reader:
    def __init__(self, root, maximum=8 * 1024 * 1024):
        self.root = Path(root)
        self.warnings = []
        self.bytes_read = 0
        self.maximum = maximum
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError('Run directory is unavailable or is a symlink')

    def warn(self, message):
        if len(self.warnings) < 100:
            self.warnings.append(message[:300])

    def text(self, relative, maximum=8000):
        path = self.root / relative
        cursor = self.root
        for part in path.relative_to(self.root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError('Symlinks are unavailable in change history')
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Change history requires regular files')
            remaining = self.maximum - self.bytes_read
            raw = stream.read(min(maximum + 1, max(0, remaining)))
        self.bytes_read += len(raw)
        if remaining <= maximum and len(raw) == remaining:
            self.warn(f'{relative}: aggregate preview limit reached; counts or source unavailable')
            return None
        if len(raw) > maximum:
            self.warn(f'{relative}: preview limit exceeded; inspect the original file locally')
            return None
        return raw.decode('utf-8')

    def json(self, relative, default, maximum=2 * 1024 * 1024):
        raw = self.text(relative, maximum)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            self.warn(f'{relative}: incomplete or invalid JSON snapshot')
            return default


def source_trace(reader, prefix, cfg):
    baseline = reader.text(prefix + 'repair-baseline.py')
    tools = reader.json(prefix + 'repair-tools.json', [], 512000)
    if not isinstance(tools, list) or len(tools) > 24:
        raise ValueError('Invalid bounded tool history')
    current = baseline
    steps = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get('name') not in ('read_solution', 'write_solution', 'run_tests'):
            raise ValueError('Invalid repair tool history')
        before = current
        attempted = (tool.get('arguments') or {}).get('source') if tool['name'] == 'write_solution' else None
        if attempted is not None and (not isinstance(attempted, str) or len(attempted.encode()) > 8000):
            raise ValueError('Source attempt exceeds its bounded contract')
        applied = tool['name'] == 'write_solution' and tool.get('status') == 'completed'
        # Missing baseline/write data stays unknown rather than fabricating a diff.
        if applied and attempted is not None:
            current = attempted
        entry = {key: tool.get(key) for key in ('id', 'name', 'status', 'startedAt', 'finishedAt')}
        entry.update(before=before, after=current, attemptedSource=attempted, applied=applied,
                     changed=before is not None and current is not None and before != current,
                     patch=patch(before, current) if before is not None and current is not None else None,
                     error=str(tool.get('error', ''))[:2000])
        if tool['name'] == 'run_tests' and tool.get('status') == 'completed':
            try:
                result = json.loads(tool.get('result', ''))
                if type(result.get('passed')) is int and type(result.get('total')) is int:
                    entry.update(visiblePassed=result['passed'], visibleTotal=result['total'])
            except (ValueError, TypeError):
                reader.warn(prefix + 'repair-tools.json: test result unavailable')
        steps.append(entry)
    candidate = reader.text(prefix + 'repair-candidate.py')
    return {'baseline': baseline, 'currentSource': current, 'candidate': candidate, 'steps': steps,
            'candidateMatchesTrace': candidate is not None and current is not None and candidate == current,
            'taskId': cfg.get('taskId'), 'taskPrompt': cfg.get('fixture', {}).get('prompt'),
            'skill': {'body': cfg.get('skill', {}).get('body'),
                                                  'hash': cfg.get('skill', {}).get('hash')}}


def snapshot(service, run_id, rollout='', offset=0, limit=20):
    if not re.fullmatch(r'RUN-[A-Za-z0-9-]+', run_id) or rollout and not re.fullmatch(r'R\d{4}', rollout):
        raise ValueError('Invalid Run or rollout identity')
    if type(offset) is not int or not 0 <= offset <= 200 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Invalid change history page')
    run = service.get_run(run_id)
    if run.get('task') not in ('gepa-evolution', 'nanobot-repair'):
        raise ValueError('Source history is available for Python repair and GEPA only')
    directory = service.local / 'runs' / run_id
    if (service.local / 'runs').is_symlink():
        raise ValueError('Run storage cannot be a symlink')
    reader = Reader(directory)
    gepa = run['task'] == 'gepa-evolution'
    # A bank run freezes up to 50 bounded fixtures; preserve history for that
    # configuration without relaxing the existing 8 MiB aggregate read bound.
    cfg = reader.json('gepa-config.json' if gepa else 'repair-config.json', {}, 4 * 1024 * 1024 if gepa else 128000)
    if not isinstance(cfg, dict):
        raise ValueError('Invalid saved configuration')
    baseline = cfg.get('baseline', {}).get('skill', {}) if gepa else cfg.get('skill', {})
    history = [{'id': 'baseline', 'kind': 'baseline', 'before': baseline.get('body'),
                'after': baseline.get('body'), 'changed': False, 'note': 'Frozen baseline Skill'}]
    rows = []
    if gepa:
        ledger = reader.json('gepa-rollouts.json', [])
        proposals = reader.json('gepa-proposals.json', [])
        search = reader.json('gepa-search.json', {})
        selection = reader.json('gepa-selection.json', {})
        if not isinstance(search, dict) or not isinstance(selection, dict):
            raise ValueError('Invalid saved Skill selection')
        if not isinstance(ledger, list) or len(ledger) > 200 or not isinstance(proposals, list) or len(proposals) > 16:
            raise ValueError('GEPA history exceeds bounded limits')
        for row in ledger:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'R\d{4}', row['id']):
                raise ValueError('Invalid persisted rollout identity')
        by_id = {row['id']: row for row in ledger}
        parent = directory / 'rollouts'
        if parent.is_symlink():
            raise ValueError('Rollout storage cannot be a symlink')
        children = []
        if parent.is_dir():
            for index, child in enumerate(parent.iterdir()):
                if index >= 400 or len(children) >= 200:
                    raise ValueError('Too many rollout directories')
                if re.fullmatch(r'R\d{4}', child.name):
                    children.append(child.name)
        identities = sorted(set(by_id) | set(children))
        if len(identities) > 200:
            raise ValueError('Too many rollouts')
        child_configs = {}
        task_ids = []
        attempts = {}
        ordinals = {}
        for identifier in identities:
            task_id = by_id.get(identifier, {}).get('taskId')
            if task_id is None:
                child_configs[identifier] = reader.json('rollouts/' + identifier + '/repair-config.json', {}, 128000)
                task_id = child_configs[identifier].get('taskId')
            task_ids.append(task_id)
            attempts[task_id] = attempts.get(task_id, 0) + 1
            ordinals[identifier] = attempts[task_id] if task_id is not None and None not in task_ids else None
        task_catalog = catalog(cfg, task_ids)
        metadata = {task['id']: task for task in task_catalog['tasks']}
        for identifier in identities[offset:offset + limit]:
            row = by_id.get(identifier, {})
            prefix = 'rollouts/' + identifier + '/'
            child = child_configs.get(identifier)
            if child is None:
                child = reader.json(prefix + 'repair-config.json', {}, 128000)
                child_configs[identifier] = child
            body = row.get('body', child.get('skill', {}).get('body'))
            projected = {'id': identifier, 'taskId': row.get('taskId', child.get('taskId')),
                         'stage': row.get('stage'), 'score': row.get('score'), 'completed': identifier in by_id,
                         'skillChanged': body != baseline.get('body') if body is not None else None,
                         'attempt': ordinals[identifier], 'question': metadata.get(row.get('taskId', child.get('taskId')))}
            projected['records'] = records(reader, prefix, child, {**row, **projected}, baseline, proposals)
            rows.append(projected)
        if not rollout and identities:
            rollout = identities[min(offset, len(identities) - 1)]
        if rollout and rollout not in identities:
            raise KeyError('Rollout not found')
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError('Invalid saved proposal')
            before, after = proposal.get('parentBody'), proposal.get('body')
            if not all(isinstance(body, str) and len(body.encode()) <= 8000 for body in (before, after)):
                raise ValueError('Invalid Skill proposal body')
            score = next((search.get('validationScores', [])[i] for i, c in enumerate(search.get('candidates', []))
                          if c.get('skill_body') == after and i < len(search.get('validationScores', []))), None)
            history.append({'id': proposal.get('id'), 'kind': 'proposal', 'before': before, 'after': after,
                            'changed': before != after, 'patch': patch(before, after), 'validationScore': score,
                            'note': 'Matches selected Skill' if after == selection.get('skill', {}).get('body') else
                                    'Not selected' if selection else 'Selection not completed'})
        selected_body = selection.get('skill', {}).get('body')
        if selected_body is not None:
            if not isinstance(selected_body, str) or len(selected_body.encode()) > 8000:
                raise ValueError('Invalid selected Skill body')
            history.append({'id': 'selection', 'kind': 'selection', 'before': baseline.get('body'), 'after': selected_body,
                            'changed': baseline.get('body') != selected_body,
                            'patch': patch(baseline.get('body', ''), selected_body),
                            'note': 'Selection frozen; release requires completed independent review and approval'})
        else:
            history.append({'id': 'pending', 'kind': 'pending', 'before': baseline.get('body'), 'after': None,
                            'changed': False, 'note': 'No frozen selection; no evolution outcome confirmed'})
        prefix = 'rollouts/' + rollout + '/' if rollout else None
        child_cfg = child_configs.get(rollout)
        if child_cfg is None:
            child_cfg = reader.json(prefix + 'repair-config.json', {}, 128000) if prefix else {}
        trace = source_trace(reader, prefix, child_cfg) if prefix else None
        total = len(identities)
    else:
        if rollout:
            raise ValueError('Single repair runs have no GEPA rollout')
        trace = source_trace(reader, '', cfg)
        history[0]['note'] = 'Fixed Skill throughout this repair; no Skill proposal or activation'
        total = 0
    result = run.get('gepaResult' if gepa else 'repairResult') or {}
    return {'schemaVersion': 1, 'runId': run_id, 'runStatus': run['status'], 'task': run['task'],
            'verified': run['status'] == 'completed' and result.get('checksPassed') is True,
            'rollouts': rows, 'totalRollouts': total, 'offset': offset, 'limit': limit,
            'selectedRollout': rollout, 'trace': trace, 'skillHistory': history,
            **({'taskCatalog': task_catalog} if gepa else {}),
            'warnings': reader.warnings, 'historyOnly': True}
