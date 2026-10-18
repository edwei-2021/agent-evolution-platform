"""Exact exploration integration: real pinned SDKs, scripted loopback model."""
import io
import json
import subprocess
import unittest
import zipfile
import challenge_workflow_test as fixture
from challenge_workflow_test import Model, skill_snapshot, build_bundle, verify, ROOT, ROLES


class ExplorationWorkflowTests(unittest.TestCase):
    setUp=fixture.ChallengeWorkflowTests.setUp
    tearDown=fixture.ChallengeWorkflowTests.tearDown

    def test_exploration_perfect_training_duplicate_retention_full_coverage_review_and_approval(self):
        Model.mode='explore'
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(ROLES)]}
        # 31 search + 12 final; 262 request slots; scripted repairs use
        # exactly one visible-test tool and three trusted batches/rollout.
        # 120 startup + 262*10 requests + 43*20 verifiers/tools + 30 = 3630s.
        options={'profile':'bank','bankRevision':1,'searchMode':'explore','metricBudget':31,'proposalBudget':4,
                 'taskCallBudget':6,'callTimeoutSeconds':10,'maxSeconds':3630,'providerRevision':1,'expectedRevision':1}
        run=self.service.start(registry,'exploration-proof','gepa-evolution',options)
        self.assertTrue(self.service.completion_event.wait(3660),'No persisted terminal result')
        done=self.service.get_run(run['id']);self.assertEqual(done['status'],'completed',done.get('error') or str(done['agents']))
        result=done['gepaResult'];e=result['exploration']
        self.assertEqual((e['generated'],e['uniqueNew'],e['duplicates'],e['validatedNew']),(4,2,2,2))
        self.assertEqual((e['skippedDuplicates'],e['savedCandidateEvaluations']),(2,4))
        self.assertEqual((e['trainingTested'],e['trainingTotal']),(6,6))
        self.assertTrue(result['eligible']);self.assertEqual(result['metricEvaluations'],21)
        directory=self.service.local/'runs'/run['id'];ledger=json.loads((directory/'gepa-rollouts.json').read_text())
        self.assertEqual(len(ledger),33)
        tools=[json.loads((directory/'rollouts'/r['id']/'repair-tools.json').read_text()) for r in ledger]
        self.assertTrue(all(len(t)<=3 and sum(s['name']=='run_tests' for s in t)<=1 for t in tools))
        batches=self.service.logs.list(run_id=run['id'],query='STEP_COMPLETED trusted-tests.batch',limit=500)
        self.assertEqual(batches['matched'],3*len(ledger))
        self.assertEqual(result['calls'],len(Model.calls));self.assertLessEqual(len(Model.calls),262)
        reflection=[c for c in Model.calls if c['messages'][0]['content']==fixture.REFLECTION_SYSTEM]
        self.assertEqual([c['temperature'] for c in reflection],[0.7,0.7,0.7,1.0])
        self.assertTrue(all(c['temperature']==0 for c in Model.calls if c not in reflection))
        proposals=json.loads((directory/'gepa-proposals.json').read_text());train={q['id'] for q in run['gepaConfig']['datasetSnapshot']['data']['train']}
        self.assertTrue(all(t['taskId'] in train for p in proposals for t in p['training']))
        self.assertTrue(all(t['score']==1 for p in proposals for t in p['training']))
        self.assertEqual(verify(directory),result)
        calls=len(Model.calls);archive=skill_snapshot(self.service.root,run['id'])
        self.assertEqual(len(archive['records']),4)
        self.assertEqual(archive['records'][0]['instruction']['text'],archive['records'][1]['instruction']['text'])
        self.assertFalse(archive['records'][0]['conditions']['skipPerfectScore'])
        self.assertEqual(archive['records'][2]['conditions']['strategy'],'tool-policy')
        self.assertEqual(archive['records'][1]['duplicateOf'],'P001')
        self.assertEqual(archive['records'][1]['novelty'],'duplicate')
        self.assertEqual([d['accepted'] for d in archive['searchAudit']['decisions']],[True,False,False,True])
        self.assertEqual(archive['searchAudit']['decisions'][1]['reason'],'duplicate-before-evaluation')
        with zipfile.ZipFile(io.BytesIO(build_bundle(self.service.root,run_id=run['id']))) as bundle:
            exported=json.loads(bundle.read('skills/'+run['id']+'.json'))
            self.assertEqual(len(exported['records']),4)
            self.assertEqual(exported['outcome']['eligible'],True)
            self.assertEqual(exported['searchAudit']['exploration']['uniqueNew'],2)
        parser="""import fs from 'node:fs';import {validateGepaRun} from './dist/js/runtime-client.js';
import {gepaResultsView} from './dist/js/gepa-results-view.js';
const run=JSON.parse(fs.readFileSync(0,'utf8'));validateGepaRun(run);
const html=gepaResultsView({data:{gepa:{latestRun:run,versions:[],activeVersionId:run.gepaConfig.baseline.id}}});
if(!html.includes('不同新本文 2 個')||!html.includes('訓練覆蓋 6/6'))process.exit(1);
run.gepaResult.exploration.uniqueNew=3;
try{validateGepaRun(run);process.exit(2);}catch(e){if(!e.message.includes('探索'))throw e;}
"""
        parsed=subprocess.run(['node','--input-type=module','-e',parser],cwd=ROOT,input=json.dumps(done),text=True,capture_output=True,timeout=10)
        self.assertEqual(parsed.returncode,0,parsed.stdout+parsed.stderr)
        self.assertEqual(len(Model.calls),calls)
        self.service.gepa.approve(run['id'],1)
        path=directory/'gepa-proposals.json';changed=json.loads(path.read_text())
        changed[0]['input']=json.dumps({'candidate':changed[0]['candidate'],'training':changed[0]['training']})
        write_text=json.dumps(changed);path.write_text(write_text)
        with self.assertRaisesRegex(ValueError,'Reflection (request|input) drift'):verify(directory)

if __name__=='__main__':unittest.main()
