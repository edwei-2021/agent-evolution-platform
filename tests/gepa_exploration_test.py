"""Coverage, bounded proposals, neutral moves and evidence retention contracts."""
import io
import json
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gepa_exploration import (CoverageSampler, NovelNonRegression, proposal_context, STRATEGIES,
                              POLICY, duplicate_of, reflection_temperature)
from gepa_store import GepaStore
from export_diagnostics import build_bundle
from skill_archive import snapshot
from skill_audit import Generation
from skill_engine import write
import skill_archive_test as archive_fixture
from challenge_bank_test import Service
from serve_gui import GuiHandler, DIST


class ExplorationTests(unittest.TestCase):
    def test_failure_memory_survives_perfect_batch_and_duplicate_temperature_changes_only_reflection(self):
        cfg={'searchMode':'explore','explorationPolicy':POLICY,'baseline':{'skill':{'body':'baseline'}}}
        failed={'taskId':'TRAIN-failed','rolloutId':'R0001','score':0,'taskOutcome':'call-limit',
                'tools':[{'error':'Unavailable call: isspace'}],
                'feedback':{'visible':{'passed':1,'total':3,'cases':'PRIVATE_ANSWERS'}}}
        proposals=[{'id':'P001','body':'new workflow','training':[failed]},
                   {'id':'P002','body':'new  workflow','training':[]},
                   {'id':'P003','body':'new workflow','training':[]}]
        context=proposal_context({'skill_body':'baseline'},[{'taskId':'TRAIN-perfect','score':1}],proposals,cfg)
        e=context['exploration']
        self.assertEqual(e['consecutiveDuplicates'],2);self.assertEqual(e['temperature'],1)
        self.assertEqual(e['failureLessons'][0]['taskId'],'TRAIN-failed')
        self.assertEqual(e['failureLessons'][0]['toolRejections'],['Unavailable call: isspace'])
        self.assertNotIn('PRIVATE_ANSWERS',json.dumps(e))
        self.assertEqual(duplicate_of('new\nworkflow',proposals,'baseline'),'P001')
        self.assertEqual(duplicate_of(' baseline ',proposals,'baseline'),'baseline')
        self.assertEqual(reflection_temperature({},proposals),0)

    def test_smoke_and_full_can_freeze_explicit_exploration_while_omitted_mode_stays_standard(self):
        from gepa_dataset import skill
        with tempfile.TemporaryDirectory() as root:
            service=Service(root);service.closed=False
            provider={'revision':1,'endpoint':'http://127.0.0.1:1','config':{'model':'fixture','maxTokens':1024,'inferenceTimeout':120}}
            service.ollama=SimpleNamespace(lock=threading.RLock(),frozen=lambda:provider)
            store=object.__new__(GepaStore);store.service=service
            store.snapshot=Mock(return_value={'revision':1,'active':{'id':'GSV-baseline','skill':skill('baseline')},
                'sdk':{'available':True,'version':'0.3.5'},'optimizer':{'available':True,'version':'0.1.4'}})
            options={'profile':'smoke','maxSeconds':1800,'callTimeoutSeconds':120,'taskCallBudget':8,
                'metricBudget':10,'proposalBudget':2,'providerRevision':1,'expectedRevision':1}
            for profile,metrics in [('smoke',10),('full',26)]:
                frozen=store.freeze({**options,'profile':profile,'metricBudget':metrics,'searchMode':'explore'})
                self.assertEqual(frozen['explorationPolicy'],POLICY)
                self.assertIsInstance(frozen['searchSeed'],int)
            legacy=store.freeze(options)
            self.assertNotIn('searchSeed',legacy);self.assertNotIn('explorationPolicy',legacy)

    def test_actual_search_skips_duplicate_children_and_stops_stagnation_without_fabricated_metrics(self):
        from gepa_dataset import skill
        from gepa_sdk import search
        with tempfile.TemporaryDirectory() as root:
            service=Service(root);directory=Path(root)/'RUN-native';directory.mkdir()
            cfg={'profile':'bank','searchMode':'explore','explorationPolicy':POLICY,'searchSeed':19,
                'baseline':{'id':'GSV-baseline','skill':skill('baseline')},'datasetSnapshot':service.challenges.freeze(1),
                'reflectionBatch':2,'metricBudget':87,'proposalBudget':16,'callBudget':1204,
                'deadlineEpoch':time.time()+60,'logRoot':root}
            session=SimpleNamespace(cfg=cfg,directory=directory,ledger=[],calls=[],proposals=[],fatal=None)
            def rollout(task,body,stage):
                row={'id':f'R{len(session.ledger)+1:04d}','taskId':task['id'],'stage':stage,'body':body,'score':1}
                session.ledger.append(row)
                return row,{'rolloutId':row['id'],'taskId':task['id'],'score':1}
            session.rollout=rollout;temperatures=[]
            def runner(child,config,*args):
                temperatures.append(config['reflectionTemperature'])
                return SimpleNamespace(call=lambda *args:{'choices':[{'message':{'content':json.dumps({'skill_body':'A different operational workflow.'})}}]})
            with patch('gepa_sdk.Session',return_value=session),patch('gepa_sdk.GlobalRunner',side_effect=runner),patch('sys.stdout',new=io.StringIO()):
                search(directory,cfg)
            result=json.loads((directory/'gepa-search.json').read_text())
            audit=json.loads((directory/'gepa-search-audit.json').read_text())
            self.assertEqual(len(session.proposals),7)
            self.assertEqual(result['metricCalls'],22);self.assertEqual(result['sdkMetricCalls'],22)
            self.assertEqual(result['bestIndex'],0);self.assertEqual(len(result['candidates']),2)
            self.assertEqual(temperatures,[.7,.7,.7,1,1,1,1])
            self.assertIn('duplicate-stagnation',audit['stop']['reasons'])
            self.assertEqual(audit['exploration']['savedCandidateEvaluations'],12)
            self.assertEqual(audit['exploration']['trainingTested'],6)
            self.assertEqual([e.get('reason') for e in audit['decisions'][1:]],['duplicate-before-evaluation']*6)

    def test_native_smoke_and_full_exploration_do_not_skip_perfect_training(self):
        from gepa import optimize
        from gepa.core.adapter import EvaluationBatch
        from gepa_dataset import dataset
        for profile,mini,metrics in [('smoke',1,6),('full',3,26)]:
            proposals=[];data=dataset(profile)
            class Adapter:
                def evaluate(self,batch,candidate,capture_traces=False):
                    return EvaluationBatch(outputs=[{} for _ in batch],scores=[1.0]*len(batch),
                        trajectories=list(batch) if capture_traces else None,num_metric_calls=len(batch))
                def make_reflective_dataset(self,candidate,eval_batch,components_to_update):return {'skill_body':eval_batch.trajectories}
                def propose_new_texts(self,*args):
                    proposals.append(args);return {'skill_body':'Different workflow'}
            with self.subTest(profile=profile),patch('sys.stdout',new=io.StringIO()):
                result=optimize(seed_candidate={'skill_body':'baseline'},trainset=data['train'],valset=data['validation'],
                    adapter=Adapter(),batch_sampler=CoverageSampler(mini,17),skip_perfect_score=False,
                    acceptance_criterion=NovelNonRegression(),max_metric_calls=metrics,stop_callbacks=lambda _:len(proposals)>=1,
                    use_merge=False,cache_evaluation=False,display_progress_bar=False)
                self.assertEqual(len(proposals),1);self.assertEqual(len(result.candidates),2)
                self.assertEqual(result.total_metric_calls,metrics);self.assertEqual(result.best_idx,0)

    def test_actual_http_route_forwards_explicit_mode_and_rejects_unknown_fields_without_model_work(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root);service.start=Mock(return_value={'id':'RUN-route-fixture'})
            class Quiet(GuiHandler):
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(DIST)));server.runtime=service
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            body={'registry':{'agents':[]},'requestId':'fixture','profile':'bank','bankRevision':1,'searchMode':'explore',
                  'metricBudget':87,'proposalBudget':12,'taskCallBudget':10,'maxSeconds':7200,
                  'callTimeoutSeconds':120,'providerRevision':1,'expectedRevision':1}
            def post(value):
                connection=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                connection.request('POST','/api/v1/gepa/runs',json.dumps(value),{'Content-Type':'application/json','X-Lab-Token':service.csrf_token})
                response=connection.getresponse();response.read();status=response.status;connection.close();return status
            try:
                self.assertEqual(post(body),202)
                options=service.start.call_args.args[-1]
                self.assertEqual(options['searchMode'],'explore');self.assertEqual(options['proposalBudget'],12)
                self.assertEqual(post({**body,'unknown':True}),400);self.assertEqual(service.start.call_count,1)
            finally:server.shutdown();server.server_close();thread.join()

    def test_short_batches_cover_all_training_ids_before_any_repeat_and_replay_seed(self):
        loader=SimpleNamespace(all_ids=lambda:list(range(5)))
        def take(seed):
            sampler=CoverageSampler(2,seed)
            batches=[sampler.next_minibatch_ids(loader,None) for _ in range(3)]
            self.assertEqual([len(b) for b in batches],[2,2,1])
            self.assertEqual(set(sum(batches,[])),set(range(5)))
            self.assertEqual(len(sum(batches,[])),5)
            self.assertEqual(len(sampler.next_minibatch_ids(loader,None)),2)
            return batches
        self.assertEqual(take(37),take(37));self.assertNotEqual(take(37),take(71))

    def test_equal_training_scores_allow_distinct_candidate_but_duplicates_and_regressions_do_not(self):
        state=SimpleNamespace(program_candidates=[{'skill_body':'baseline'}]);criterion=NovelNonRegression()
        def proposal(body,after):
            return SimpleNamespace(candidate={'skill_body':body},subsample_scores_before=[1,1],subsample_scores_after=after)
        self.assertTrue(criterion.should_accept(proposal('different',[1,1]),state))
        self.assertFalse(criterion.should_accept(proposal('baseline',[1,1]),state))
        self.assertEqual(criterion.reject_reason(proposal('baseline',[1,1]),state),'duplicate-instructions')
        self.assertFalse(criterion.should_accept(proposal('different',[0,1]),state))

    def test_context_has_distinct_strategies_and_only_supplied_training_and_prior_instructions(self):
        prior=[];names=[]
        for i in range(16):
            value=proposal_context({'skill_body':'parent'},[{'taskId':'TRAIN'}],prior,{'searchMode':'explore'})
            names.append(value['exploration']['strategy'])
            self.assertEqual(len(value['exploration']['recentInstructions']),min(i,3))
            self.assertEqual(value['training'],[{'taskId':'TRAIN'}])
            prior.append({'body':f'Instruction {i}'})
        self.assertEqual(len(set(names)),len(STRATEGIES))
        self.assertEqual(proposal_context({},[],prior,{}),{'candidate':{},'training':[]})

    def test_coverage_and_mode_limits_fail_before_sdk_or_model_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(root)
            store=object.__new__(GepaStore);store.service=service
            store.snapshot=Mock(side_effect=AssertionError('No SDK probe'))
            options={'profile':'bank','bankRevision':1,'searchMode':'explore','metricBudget':87,'proposalBudget':12,
                     'taskCallBudget':10,'maxSeconds':7200,'callTimeoutSeconds':120,'providerRevision':1,'expectedRevision':1}
            for change in [{'metricBudget':23},{'proposalBudget':2},{'metricBudget':121},{'proposalBudget':17},{'searchMode':'unknown'}]:
                with self.subTest(change=change),self.assertRaises(ValueError):store.freeze({**options,**change})
            store.snapshot.assert_not_called()

    def test_real_gepa_perfect_seed_generates_twelve_distinct_candidates_and_validates_neutral_moves(self):
        from gepa import optimize
        from gepa.core.adapter import EvaluationBatch
        train=[{'id':f'T{i}'} for i in range(6)];val=[{'id':f'V{i}'} for i in range(3)]
        proposed=[];evaluated=[]
        class Adapter:
            def evaluate(self,batch,candidate,capture_traces=False):
                evaluated.append((list(batch),dict(candidate),capture_traces))
                return EvaluationBatch(outputs=[{} for _ in batch],scores=[1.0 for _ in batch],
                    trajectories=list(batch) if capture_traces else None,num_metric_calls=len(batch))
            def make_reflective_dataset(self,candidate,eval_batch,components_to_update):
                return {'skill_body':eval_batch.trajectories}
            def propose_new_texts(self,candidate,reflective_dataset,components_to_update):
                proposed.append(reflective_dataset)
                return {'skill_body':f'Strategy {len(proposed)}: check the contract.'}
        with patch('sys.stdout',new=io.StringIO()):
            result=optimize(seed_candidate={'skill_body':'baseline'},trainset=train,valset=val,adapter=Adapter(),
                batch_sampler=CoverageSampler(2,21),skip_perfect_score=False,acceptance_criterion=NovelNonRegression(),
                use_merge=False,cache_evaluation=False,max_metric_calls=87,
                stop_callbacks=lambda state:len(proposed)>=12,display_progress_bar=False,seed=21)
        self.assertEqual(len(proposed),12);self.assertEqual(len(result.candidates),13)
        self.assertEqual(result.total_metric_calls,87);self.assertEqual(result.best_idx,0)
        first_epoch=[t['id'] for item in proposed[:3] for t in item['skill_body']]
        self.assertEqual(set(first_epoch),{t['id'] for t in train});self.assertEqual(len(first_epoch),6)
        self.assertTrue(all(t['id'].startswith('T') for item in proposed for t in item['skill_body']))
        validation=[b for b,c,traces in evaluated if all(t['id'].startswith('V') for t in b)]
        self.assertEqual(len(validation),13)


class ExplorationArchiveTests(unittest.TestCase):
    setUp=archive_fixture.SkillArchiveTests.setUp
    tearDown=archive_fixture.SkillArchiveTests.tearDown
    run_record=archive_fixture.SkillArchiveTests.run_record
    def test_sixteen_candidates_and_strategy_conditions_survive_actual_diagnostic_zip(self):
        rid,directory=self.run_record();self.cfg.update(searchMode='explore',searchSeed=17,proposalBudget=16)
        records=[]
        for i in range(16):
            identifier=f'P{i+1:03d}';body=f'Use distinct strategy {i+1}.'
            with Generation(directory,identifier,self.cfg,self.base,[],'gepa-worker',strategy=STRATEGIES[i][0],seed=17) as audit:
                audit.generated({'body':body})
            records.append({'id':identifier,'body':body,'parentBody':self.base['body'],'training':[]})
        write(directory/'gepa-proposals.json',records)
        write(directory/'gepa-search-audit.json',{'mode':'explore','seed':17,'decisions':[
            {'proposalId':'P001','accepted':False,'reason':'duplicate-instructions','raw':'PRIVATE_SOURCE'}]})
        projected=snapshot(self.root,rid)
        self.assertEqual(len(projected['records']),16)
        with zipfile.ZipFile(io.BytesIO(build_bundle(self.root,run_id=rid))) as bundle:
            exported=json.loads(bundle.read('skills/'+rid+'.json'))
        self.assertEqual(len(exported['records']),16)
        self.assertEqual(exported['records'][-1]['conditions']['strategy'],'synthesis')
        self.assertEqual(exported['records'][-1]['conditions']['searchMode'],'explore')
        self.assertNotIn('PRIVATE_SOURCE',json.dumps(exported))
        # The second history consumer also accepts baseline + 16 proposals +
        # pending/selection; its former ten-entry cap rejected default runs.
        from change_trace import snapshot as changes_snapshot
        write(directory/'gepa-config.json',{'baseline':{'skill':self.base}})
        service=SimpleNamespace(local=self.root/'.local',get_run=lambda _: {'id':rid,'task':'gepa-evolution','status':'failed'})
        page=changes_snapshot(service,rid)
        self.assertEqual(len(page['skillHistory']),18)
        parser="""import fs from 'node:fs';import {validateChanges} from './dist/js/changes-client.js';
const page=JSON.parse(fs.readFileSync(0,'utf8'));validateChanges(page);
page.skillHistory.push(page.skillHistory[0]);try{validateChanges(page);process.exit(1);}catch{}
"""
        completed=subprocess.run(['node','--input-type=module','-e',parser],cwd=Path(__file__).resolve().parents[1],input=json.dumps(page),text=True,capture_output=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)


if __name__=='__main__':unittest.main()
