"""Real pinned SDKs and role processes, authenticated loopback Strata fixtures."""
import json
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from model_provider import STRATA_DEFAULTS
import llm_test
import repair_test
import gepa_test

class StrataWorkflows(unittest.TestCase):
    def configure(self, fixture, model):
        env=patch.dict(os.environ,{'OPENAI_API_KEY':'workflow-fixture-secret'});env.start();self.addCleanup(env.stop)
        original=model.do_POST;observed=[]
        def authenticated(handler):
            observed.append((handler.path,handler.headers.get('Authorization')))
            if handler.headers.get('Authorization')!='Bearer workflow-fixture-secret':
                handler.send_error(401);return
            return original(handler)
        auth=patch.object(model,'do_POST',authenticated);auth.start();self.addCleanup(auth.stop)
        fixture.setUp();self.addCleanup(fixture.tearDown)
        old=fixture.service.ollama.state()['config']
        fixture.service.ollama.save({**STRATA_DEFAULTS,'baseUrl':f'http://127.0.0.1:{fixture.model.server_port}/v1',
            'model':old['model'],'maxTokens':old['maxTokens'],'inferenceTimeout':old['inferenceTimeout']},1)
        self.assertEqual(model.calls,[])
        return observed
    def assert_provider(self, fixture, calls, observed):
        self.assertTrue(calls);self.assertTrue(all(c.get('reasoning_effort')=='none' for c in calls))
        self.assertTrue(all(p=='/v1/chat/completions' and a=='Bearer workflow-fixture-secret' for p,a in observed))
        self.assertEqual(len(observed),len(calls));self.assertFalse(fixture.service.ollama.operation.locked())
        for path in (Path(fixture.temp.name)/'.local').rglob('*.json'):
            self.assertNotIn('workflow-fixture-secret',path.read_text())
    def test_llm_reflection_review_approval_and_rollback(self):
        f=llm_test.LlmWorkflowTests('test_actual_worker_reflection_evaluation_review_and_versions')
        observed=self.configure(f,llm_test.MockModel);llm_test.MockModel.mode='stream'
        original=f.options;f.options=lambda revision=1:{**original(revision),'providerRevision':2}
        f.test_actual_worker_reflection_evaluation_review_and_versions()
        self.assert_provider(f,llm_test.MockModel.calls,observed)
    @unittest.skipUnless(repair_test.SDK,'Requires pinned nanobot SDK')
    def test_real_nanobot_streamed_tools_and_independent_reviewer(self):
        f=repair_test.SdkWorkflowTests('test_fragmented_sse_tool_arguments_reconstruct_and_tampering_is_rejected')
        observed=self.configure(f,repair_test.Model);repair_test.Model.mode='stream'
        registry=llm_test.registry()
        run=f.service.start(registry,'strata-repair','nanobot-repair',{'maxSeconds':f.workflow_seconds,'callTimeoutSeconds':10,'callBudget':8,'providerRevision':2})
        done=f.finish(run['id']);self.assertEqual(done['status'],'completed',done.get('error'))
        self.assertTrue(done['repairResult']['repairPassed']);self.assertEqual(done['repairResult']['toolCalls'],3)
        directory=f.service.local/'runs'/run['id'];self.assertEqual(repair_test.verify(directory),done['repairResult'])
        config=json.loads((directory/'repair-config.json').read_text());self.assertEqual(config['provider']['kind'],'strata')
        calls=json.loads((directory/'repair-calls.json').read_text());self.assertTrue(calls[1]['streamEvents'])
        self.assertEqual(calls[-1]['request']['tools'],[]);self.assertEqual(calls[-1]['request']['tool_choice'],'none')
        self.assert_provider(f,repair_test.Model.calls,observed)
        calls[0]['request']['reasoning_effort']='high';(directory/'repair-calls.json').write_text(json.dumps(calls))
        with self.assertRaises(ValueError):repair_test.verify(directory)
    @unittest.skipUnless(gepa_test.SDK,'Requires pinned nanobot and GEPA SDKs')
    def test_real_gepa_search_final_review_approval_rollback_and_tamper_gate(self):
        f=gepa_test.GepaWorkflowTests('test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate')
        observed=self.configure(f,gepa_test.Model)
        original=f.start;f.start=lambda **changes:original(**{'providerRevision':2,**changes})
        f.test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate()
        self.assert_provider(f,gepa_test.Model.calls,observed)

if __name__=='__main__':unittest.main()
