"""Versioned synthetic repair benchmark; operation families never cross splits."""
from repair_fixture import BASELINE, SKILL, digest

DATASET_VERSION='bounded-python-families-v1'
GROUPS={'train':['clamp','absolute-offset','minimum','maximum'],
        'validation':['sign','positive-sum'],
        'heldout':['clipped-sum','span','distance','threshold']}
CASES=[(3,-2,5),(-7,-3,2),(9,4,1),(0,0,0),(-11,7,7),(6,-8,-1)]

def contract(group,k):
    return {
      'clamp':f'If lower > upper raise ValueError; otherwise return max(lower,min(value,upper)) + ({k}).',
      'absolute-offset':f'Return the absolute difference between value and lower, plus upper + ({k}).',
      'minimum':f'Return the minimum of value, lower and upper + ({k}). Add the offset after finding the minimum.',
      'maximum':f'Return the maximum of value, lower and upper + ({k}). Add the offset after finding the maximum.',
      'sign':f'Return -1 for negative value, 0 for zero, 1 for positive value, then add ({k}). Ignore lower and upper.',
      'positive-sum':f'Return max(0,value)+max(0,lower)+max(0,upper)+({k}).',
      'clipped-sum':f'If upper <= 0 raise ValueError; otherwise return max(-upper,min(value+lower,upper))+({k}).',
      'span':f'If lower > upper raise ValueError; otherwise return upper-lower+({k}). Ignore value.',
      'distance':f'Return the absolute difference between value and upper, plus ({k}). Ignore lower.',
      'threshold':f'Return lower if value < upper, otherwise return upper; then add ({k}).',
    }[group]

def expected(group,k,v,l,u):
    if group=='clamp':return 'ValueError' if l>u else max(l,min(v,u))+k
    if group=='absolute-offset':return abs(v-l)+u+k
    if group=='minimum':return min(v,l,u)+k
    if group=='maximum':return max(v,l,u)+k
    if group=='sign':return (-1 if v<0 else 1 if v>0 else 0)+k
    if group=='positive-sum':return max(0,v)+max(0,l)+max(0,u)+k
    if group=='clipped-sum':return 'ValueError' if u<=0 else max(-u,min(v+l,u))+k
    if group=='span':return 'ValueError' if l>u else u-l+k
    if group=='distance':return abs(v-u)+k
    if group=='threshold':return (l if v<u else u)+k
    raise ValueError('Unknown task family')

def dataset(profile):
    if profile not in ('smoke','full'):raise ValueError('Use smoke or full GEPA profile')
    data={}
    for split,groups in GROUPS.items():
        rows=[]
        for group in groups:
            for index,k in enumerate([-2,-1,0,1,2] if profile=='full' else [0]):
                identifier=f'PY-{group}-{index+1}'
                records=[[list(args),expected(group,k,*args)] for args in CASES]
                prompt=f'Task ID: {identifier}\nRepair solution.py. Preserve clamp(value, lower, upper). '+contract(group,k)+' Use only read_solution, write_solution and run_tests. Imports, attributes, loops, comprehensions, shell and other files are unavailable. Use comparisons, integer addition/subtraction, min/max, conditional returns and ValueError. Final tests follow after the turn.'
                rows.append({'id':identifier,'group':group,'offset':k,'fixture':{'baseline':BASELINE,'prompt':prompt,'visible':records[:3],'hidden':records[3:]}})
        data[split]=rows
    return data

def skill(body):
    if not isinstance(body,str) or not body.strip() or len(body.encode())>8000:raise ValueError('Skill body must be nonempty and at most 8 KB')
    value={**SKILL,'body':body};value['hash']=digest({key:value[key] for key in ('name','description','body')});return value

def dataset_hash(profile):return digest({'version':DATASET_VERSION,'groups':GROUPS,'data':dataset(profile)})

def data_for(config):
    if config.get('profile') == 'bank':
        from challenge_bank import validate_snapshot
        return validate_snapshot(config['datasetSnapshot'])
    return dataset(config['profile'])
