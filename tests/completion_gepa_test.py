"""Real SDK failure at V3 regex summary; original evidence survives ZIP export."""
import io
import json
import unittest
import zipfile
from unittest.mock import patch
import challenge_workflow_test as fixture
from repair_engine import SUMMARY_MESSAGE
from export_diagnostics import gepa_repair_summary


class GepaSummaryFailureTests(unittest.TestCase):
    setUp=fixture.ChallengeWorkflowTests.setUp
    tearDown=fixture.ChallengeWorkflowTests.tearDown

    def test_truncated_regex_summary_is_fatal_once_and_old_response_is_exported_without_replay(self):
        self.service.challenges.install_v3(1,3)
        original=fixture.Model.do_POST
        def handler(server):
            raw=server.rfile.read(int(server.headers['Content-Length']));body=json.loads(raw)
            if 'Task ID: CH-v3-regex-match' not in str(body['messages']):
                server.rfile=io.BytesIO(raw);return original(server)
            fixture.Model.calls.append(body)
            used=sum(m.get('role')=='tool' for m in body['messages'])
            if body['tools']:
                name='read_solution' if used==0 else 'run_tests'
                args={'path':'solution.py'} if used==0 else {}
                reply={'choices':[{'finish_reason':'tool_calls','message':{'content':None,'tool_calls':[
                    {'id':'tool-'+str(used),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}]}
                data=json.dumps(reply).encode();mime='application/json'
            else:
                event={'model':body['model'],'choices':[{'index':0,'delta':{'content':'PRIVATE_TRUNCATED_SUMMARY'},'finish_reason':'length'}],
                       'usage':{'completion_tokens':1024}}
                data=('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode();mime='text/event-stream'
            server.send_response(200);server.send_header('Content-Type',mime);server.send_header('Content-Length',str(len(data)));server.end_headers();server.wfile.write(data)
        registry={'agents':[{'id':'AG-'+str(i),'name':role,'role':role,'enabled':True} for i,role in enumerate(fixture.ROLES)]}
        with patch.object(fixture.Model,'do_POST',handler):
            run=self.service.start(registry,'summary-failure-proof','gepa-evolution',{
                'profile':'bank','bankRevision':2,'metricBudget':10,'proposalBudget':1,'taskCallBudget':6,
                'callTimeoutSeconds':10,'maxSeconds':4450,'providerRevision':1,'expectedRevision':1})
            self.assertTrue(self.service.completion_event.wait(4480))
        done=self.service.get_run(run['id']);self.assertEqual(done['status'],'failed')
        self.assertIn('finish_reason=length',done['error']);self.assertFalse(self.service.ollama.operation.locked())
        self.assertNotIn('gepaResult',done);directory=self.service.local/'runs'/run['id']
        ledger=json.loads((directory/'gepa-rollouts.json').read_text());self.assertEqual(len(ledger),2)
        self.assertTrue(all(row['stage']=='search' for row in ledger))
        self.assertFalse((directory/'gepa-selection.json').exists())
        self.assertEqual(json.loads((directory/'gepa-proposals.json').read_text()),[])
        self.assertEqual(len(fixture.Model.calls),5)
        summary=fixture.Model.calls[-1];self.assertEqual(summary['messages'][-1],SUMMARY_MESSAGE)
        self.assertEqual(summary['tools'],[])
        old_calls=len(fixture.Model.calls)
        with zipfile.ZipFile(io.BytesIO(fixture.build_bundle(self.service.root,run['id']))) as archive:
            state=json.loads(archive.read('status.json'));trace=state['runs'][0]['gepaRepairTrace']
            self.assertEqual(trace['rolloutId'],'R0003');self.assertEqual(trace['taskId'],'CH-v3-regex-match')
            call=trace['calls'][-1]
            self.assertEqual(call['status'],'failed');self.assertEqual(call['finishReason'],'length')
            self.assertEqual(call['completionCount'],1024);self.assertEqual(call['toolCallCount'],0)
            self.assertEqual(call['outputLimit'],1024);self.assertTrue(call['finalSummary'])
            self.assertNotIn('PRIVATE_TRUNCATED_SUMMARY',archive.read('status.json').decode())
        self.assertEqual(len(fixture.Model.calls),old_calls)
        # Malformed/traversal progress and a redirected rollout cannot read
        # a different artifact or dispatch a recovery request.
        (directory/'gepa-progress.json').write_text(json.dumps({'activeRollout':'../R0003'}))
        self.assertEqual(gepa_repair_summary(directory),{})
        (directory/'gepa-progress.json').write_text(json.dumps({'activeRollout':'R0004'}))
        (directory/'rollouts/R0004').symlink_to(directory/'rollouts/R0003',target_is_directory=True)
        self.assertEqual(gepa_repair_summary(directory),{})
        print('SUMMARY_FAILURE_RESULT',json.dumps({'requests':old_calls,'completedRollouts':2,'newCandidates':0,'failedFinishReason':call['finishReason']}),flush=True)
