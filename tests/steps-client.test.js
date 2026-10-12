import test from 'node:test';
import assert from 'node:assert/strict';
import {StepsClient,validateSteps} from '../dist/js/steps-client.js';
import {stepResultsView,stepsView} from '../dist/js/steps-view.js';
const stamp='2026-10-12T08:00:00Z';
const sample=(id='RUN-test')=>({schemaVersion:1,runId:id,runStatus:'completed',steps:[{id:'a'.repeat(32),name:'trusted-tests.batch',module:'nanobot',status:'completed',startedAt:stamp,finishedAt:stamp,durationMs:30}],returnedEvents:2,matchedEvents:2,truncated:false,serverTime:stamp});
test('step validator rejects fabricated timing, duplicate IDs and invalid terminal states',()=>{
 assert.equal(validateSteps(sample()).steps.length,1);
 for(const change of [d=>d.steps[0].durationMs=-1,d=>d.steps[0].status='PASS',d=>d.steps.push({...d.steps[0]}),d=>d.steps[0].startedAt='bad',d=>d.returnedEvents=501,d=>d.runId='../outside']){const d=sample();change(d);assert.throws(()=>validateSteps(d));}
});
test('read-only step requests reject invalid run IDs and do not submit model work',async()=>{
 const paths=[];const client=new StepsClient({request:async p=>{paths.push(p);return sample();}});
 await client.select('RUN-test');assert.deepEqual(paths,['/api/v1/debug/steps/RUN-test']);assert.equal(client.data.steps[0].status,'completed');
 await assert.rejects(client.select('../outside'));assert.equal(paths.length,1);
});
test('obsolete response cannot replace a newly selected run and failure retains prior evidence',async()=>{
 let finish;const client=new StepsClient({request:p=>p.endsWith('RUN-old')?new Promise(r=>finish=r):Promise.resolve(sample('RUN-new'))});
 const old=client.select('RUN-old');await client.select('RUN-new');finish(sample('RUN-old'));await old;assert.equal(client.data.runId,'RUN-new');
 client.request=async()=>{throw Error('offline');};await client.refresh();assert.equal(client.data.runId,'RUN-new');assert.equal(client.error,'offline');
});
test('step view escapes errors, reports timing and marks incomplete killed spans honestly',()=>{
 const data=sample();data.steps[0].error='<script>bad</script>';data.steps[0].status='unreported';data.steps[0].finishedAt=null;data.steps[0].durationMs=null;data.truncated=true;
 const html=stepResultsView({data,enabled:true,lastSuccess:stamp});assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/沒有結束紀錄/);assert.match(html,/500 筆事件/);
 const view=stepsView({data,runId:'RUN-test',enabled:true},{data:{runs:[{id:'RUN-test',status:'completed'}]}});assert.match(view,/逐步執行紀錄/);assert.match(view,/data-step-run/);
});
