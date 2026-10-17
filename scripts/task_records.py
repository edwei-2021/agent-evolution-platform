"""Project saved GEPA attempts without evaluating code or consulting the live bank."""


def catalog(config, tasks):
    frozen = config.get('datasetSnapshot', {})
    data = frozen.get('data', {})
    if not isinstance(data, dict):
        raise ValueError('Invalid frozen task catalog')
    rows = []
    for split in ('train', 'validation', 'heldout'):
        for task in data.get(split, []):
            if not isinstance(task, dict) or not isinstance(task.get('id'), str):
                raise ValueError('Invalid frozen task metadata')
            rows.append({**{key: task.get(key) for key in ('id', 'title', 'difficulty', 'topic')},
                         'split': split, 'attempts': tasks.count(task['id'])})
    if len(rows) > 50:
        raise ValueError('Frozen task catalog exceeds 50 questions')
    return {'version': frozen.get('version'), 'revision': frozen.get('revision'),
            'hash': frozen.get('hash'), 'tasks': rows,
            'unassignedRollouts': tasks.count(None)}


def counts(value):
    if not isinstance(value, dict):
        return None
    passed, total = value.get('passed'), value.get('total')
    if type(passed) is not int or type(total) is not int or not 0 <= passed <= total <= 100:
        return None
    return {'passed': passed, 'total': total}


def records(reader, prefix, child, row, baseline, proposals):
    skill = child.get('skill', {})
    body = child.get('skill', {}).get('body')
    label = ('baseline' if body is not None and body == baseline.get('body') else
             next((p.get('id') for p in proposals if body is not None and p.get('body') == body), None))
    result = reader.json(prefix + 'repair-evaluation.json', {}, 128000)
    evaluation = None
    if result:
        if (not isinstance(result, dict) or result.get('taskId') != row['taskId'] or
                child.get('taskId') != row['taskId'] or
                result.get('checksPassed') is not True or type(result.get('repairPassed')) is not bool or
                any(type(result.get(key)) is not int or not 0 <= result[key] <= maximum
                    for key, maximum in (('calls', 12), ('toolCalls', 24))) or
                not row['completed'] or not row.get('evidenceHash') or
                row.get('score') != int(result.get('repairPassed', False)) or
                row['evidenceHash'] != result.get('evidenceHash')):
            reader.warn(prefix + 'repair-evaluation.json: identity or evidence unavailable; counts omitted')
        else:
            evaluation = {key: {split: counts((result.get(key) or {}).get(split))
                                for split in ('visible', 'hidden')} for key in ('baseline', 'candidate')}
            evaluation.update({key: result.get(key) for key in
                               ('repairPassed', 'calls', 'toolCalls', 'taskOutcome', 'sdkStopReason')})
    tools = reader.json(prefix + 'repair-tools.json', None, 512000)
    writes = None
    if tools is not None:
        if not isinstance(tools, list) or len(tools) > 24 or any(not isinstance(t, dict) for t in tools):
            raise ValueError('Invalid bounded attempt tools')
        current = reader.text(prefix + 'repair-baseline.py')
        writes = {'attempted': 0, 'applied': 0, 'changed': 0 if current is not None else None, 'rejected': 0}
        for tool in tools:
            if tool.get('name') != 'write_solution':
                continue
            writes['attempted'] += 1
            if tool.get('status') == 'failed':
                writes['rejected'] += 1
            if tool.get('status') == 'completed':
                writes['applied'] += 1
                source = (tool.get('arguments') or {}).get('source')
                if not isinstance(source, str) or len(source.encode()) > 8000:
                    writes['changed'] = None
                    current = None
                else:
                    if writes['changed'] is not None:
                        writes['changed'] += int(current != source)
                    current = source
    return {'skill': {key: skill.get(key) for key in ('name', 'hash')} | {'label': label},
            'writes': writes, 'evaluation': evaluation}
