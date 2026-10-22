"""Immutable independent GEPA Skill versions and evidence-backed release gates."""
import json
import time
import uuid
import secrets
from gepa_exploration import POLICY
from gepa_dataset import skill, dataset
from repair_fixture import SKILL
from repair_engine import TASK_FAILURE_POLICY
from repair_runtime import sdk_status
from gepa_runtime import gepa_status
from gepa_engine import ENGINE, provenance, verify
from gepa_comparison import POLICY as COMPARISON_POLICY
from branch_diagnostics import record as decision

class GepaStore:
    def __init__(self,service):
        self.service=service
        with service.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS gepa_versions (id TEXT PRIMARY KEY, run_id TEXT UNIQUE, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS gepa_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, active_id TEXT NOT NULL)')
            baseline={'id':'GSV-baseline','label':'G0','parentId':None,'runId':None,'createdAt':service.timestamp(),'skill':skill(SKILL['body']),'evidence':None}
            db.execute('INSERT OR IGNORE INTO gepa_versions VALUES (?,NULL,?)',(baseline['id'],json.dumps(baseline)))
            db.execute('INSERT OR IGNORE INTO gepa_state VALUES (1,1,?)',(baseline['id'],))
    def snapshot(self, *, cached_only=True):
        with self.service.lock,self.service.connect() as db:
            revision,active_id=db.execute('SELECT revision,active_id FROM gepa_state').fetchone()
            versions=[json.loads(r[0]) for r in db.execute('SELECT data FROM gepa_versions ORDER BY rowid')]
        sdk=sdk_status(self.service.root,cached_only=cached_only)
        return {'schemaVersion':1,'engine':ENGINE,'revision':revision,'activeVersionId':active_id,'active':next(v for v in versions if v['id']==active_id),'versions':versions,
          'sdk':sdk,'optimizer':gepa_status(self.service.root,sdk,cached_only=cached_only)}
    def check_revision(self,expected):
        if type(expected) is not int or expected<1:raise ValueError('expectedRevision must be a positive integer')
        if self.service.closed or self.snapshot()['revision']!=expected:raise RuntimeError('GEPA Skill state changed; refresh first')
    def freeze(self,options):
        fields={'profile','maxSeconds','callTimeoutSeconds','taskCallBudget','metricBudget','proposalBudget','providerRevision','expectedRevision'}
        if isinstance(options,dict) and options.get('profile')=='bank':fields.add('bankRevision')
        if isinstance(options,dict) and 'searchMode' in options:fields.add('searchMode')
        if isinstance(options,dict) and 'finalRepetitions' in options:
            if getattr(self.service,'canonical',None) is None:raise ValueError('Repeated final runs require canonical ledger mode')
            fields.add('finalRepetitions')
        if not isinstance(options,dict) or set(options)!=fields:raise ValueError('Unexpected GEPA options')
        mode=options.get('searchMode','standard')
        if mode not in ('standard','explore'):raise ValueError('Unknown GEPA search mode')
        repetitions=options.get('finalRepetitions',1)
        if type(repetitions) is not int or not 1<=repetitions<=3:raise ValueError('finalRepetitions must be 1..3')
        frozen=self.service.challenges.freeze(options['bankRevision']) if options['profile']=='bank' else None
        data=frozen['data'] if frozen else dataset(options['profile']);mini=2 if frozen else 1 if options['profile']=='smoke' else 3
        for key,low,high in [('maxSeconds',60,7200),('callTimeoutSeconds',10,3600),('taskCallBudget',2,12),('metricBudget',len(data['validation'])+2*mini+len(data['validation']),120 if mode=='explore' else 80),('proposalBudget',1,16 if mode=='explore' else 8)]:
            if type(options[key]) is not int or not low<=options[key]<=high:raise ValueError(f'{key} must be an integer in {low}..{high}')
        if mode=='explore' and frozen:
            batches=(len(data['train'])+mini-1)//mini
            minimum=len(data['validation'])+batches*(2*mini+len(data['validation']))
            if options['proposalBudget']<batches or options['metricBudget']<minimum:
                raise ValueError(f'Full training coverage requires proposalBudget >={batches} and metricBudget >={minimum}; reduce enabled questions if above exploration limits')
        with self.service.ollama.lock:provider=self.service.ollama.frozen()
        if type(options['providerRevision']) is not int or options['providerRevision']!=provider['revision']:raise RuntimeError('Provider settings changed; refresh first')
        if not provider['config']['model']:raise ValueError('Select and save a model first')
        if frozen and provider['config']['maxTokens']<512:raise ValueError('Challenge bank requires max output tokens >=512; save 1024 in Integrations before starting')
        self.check_revision(options['expectedRevision']);snap=self.snapshot(cached_only=False)
        if not snap['sdk']['available'] or not snap['optimizer']['available']:raise RuntimeError('Install pinned nanobot and GEPA with bash scripts/install-nanobot.sh')
        canonical_hash=None
        if getattr(self.service,'canonical',None) is not None:
            from gepa_canonical import source_snapshot, ROOT
            canonical_hash=source_snapshot(ROOT)[0]
        budget=(options['metricBudget']+2*(len(data['validation'])+repetitions*len(data['heldout'])))*options['taskCallBudget']+options['proposalBudget']
        decision(self.service.root,'M5','gepa.final-budget','frozen',repetitions=repetitions,
                 validation=len(data['validation']),heldout=len(data['heldout']),
                 finalRollouts=2*(len(data['validation'])+repetitions*len(data['heldout'])),
                 maxRollouts=options['metricBudget']+2*(len(data['validation'])+repetitions*len(data['heldout'])),
                 modelCalls=budget,workflowSeconds=options['maxSeconds'])
        return {'schemaVersion':1,'engine':ENGINE,**options,'comparisonPolicy':COMPARISON_POLICY,**({'canonicalSourceHash':canonical_hash} if canonical_hash else {}),'baseline':snap['active'],'sdk':snap['sdk'],'optimizer':snap['optimizer'],
          'provider':{**provider,'endpoint':provider['endpoint']},'callTimeoutSeconds':min(options['callTimeoutSeconds'],provider['config']['inferenceTimeout']),
          'callBudget':budget,'maxOutputTokens':budget*provider['config']['maxTokens'],'deadlineEpoch':time.time()+options['maxSeconds'],
          'reflectionBatch':mini,'counts':{s:len(rows) for s,rows in data.items()},'provenance':provenance(options['profile'],frozen),'logRoot':str(self.service.root),
          **({'datasetSnapshot':frozen,'taskFailurePolicy':TASK_FAILURE_POLICY} if frozen else {}),
          **({'searchSeed':secrets.randbelow(2**31),'explorationPolicy':POLICY} if mode=='explore' else {})}
    def approve(self,identifier,expected):
        with self.service.lock:
            self.check_revision(expected);run=self.service.get_run(identifier)
            if run.get('task')!='gepa-evolution' or run['status']!='completed' or not run.get('gepaResult',{}).get('eligible'):raise RuntimeError('Only a completed improving GEPA run can be approved')
            if run.get('gepaConfig',{}).get('canonicalJob'):
                if getattr(self.service,'canonical',None) is None or self.service.canonical.store.get(run['gepaConfig']['canonicalJob']['id'])['state']!='completed':
                    raise RuntimeError('Canonical finalization must complete before approval')
            directory=self.service.local/'runs'/identifier
            if json.loads((directory/'gepa-config.json').read_text())!=run['gepaConfig']:raise ValueError('Frozen GEPA configuration changed')
            result=verify(directory)
            if result!=run['gepaResult'] or result!=json.loads((directory/'review.json').read_text()):raise ValueError('GEPA evidence changed after review')
            if run['gepaConfig']['baseline']['id']!=self.snapshot()['activeVersionId']:raise RuntimeError('Baseline changed; start a new run')
            with self.service.connect() as db:
                if db.execute('SELECT id FROM gepa_versions WHERE run_id=?',(identifier,)).fetchone():raise RuntimeError('Run already approved')
                count=db.execute('SELECT COUNT(*) FROM gepa_versions').fetchone()[0]
                if count>=100:raise RuntimeError('Local GEPA version limit reached')
                value={'id':'GSV-'+str(uuid.uuid4()),'label':f'G{count}','parentId':run['gepaConfig']['baseline']['id'],'runId':identifier,'createdAt':self.service.timestamp(),'skill':result['selectedSkill'],'evidence':result}
                db.execute('INSERT INTO gepa_versions VALUES (?,?,?)',(value['id'],identifier,json.dumps(value)))
                db.execute('UPDATE gepa_state SET revision=?,active_id=?',(expected+1,value['id']))
            self.service.logs.append('gepa','INFO','Approved GEPA Skill version',identifier,{'versionId':value['id']})
            return self.snapshot()
    def activate(self,identifier,expected):
        with self.service.lock:
            self.check_revision(expected)
            with self.service.connect() as db:
                row=db.execute('SELECT data FROM gepa_versions WHERE id=?',(identifier,)).fetchone()
                if not row:raise KeyError('GEPA version not found')
                s=json.loads(row[0])['skill']
                if s!=skill(s['body']):raise ValueError('Skill version integrity failed')
                if self.snapshot()['activeVersionId']!=identifier:
                    db.execute('UPDATE gepa_state SET revision=?,active_id=?',(expected+1,identifier))
                    self.service.logs.append('gepa','INFO','Activated GEPA Skill version',details={'versionId':identifier})
            return self.snapshot()
