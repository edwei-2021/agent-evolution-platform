import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient} from '../dist/js/runtime-client.js';
import {validateChanges} from '../dist/js/changes-client.js';
import {changesView} from '../dist/js/changes-view.js';
import {gepaPlan} from '../dist/js/gepa-plan.js';
import {gepaView} from '../dist/js/gepa-view.js';
const source='def clamp(value, lower, upper):\n    return value\n';
const fixture=(runId='RUN-history')=>({schemaVersion:1,runId,runStatus:'failed',task:'gepa-evolution',verified:false,historyOnly:true,
 rollouts:[{id:'R0001',taskId:'PY-boundary',stage:'search',score:0,completed:true,skillChanged:false},{id:'R0002',taskId:'PY-other',stage:null,score:null,completed:false,skillChanged:false}],totalRollouts:2,offset:0,limit:20,selectedRollout:'R0001',warnings:[],
 trace:{baseline:source,currentSource:source,candidate:null,candidateMatchesTrace:false,taskId:'PY-boundary',taskPrompt:'Repair the inclusive boundary.',skill:{body:'Read, repair, test.'},
  steps:[{id:1,name:'write_solution',status:'completed',before:source,after:source,attemptedSource:source,applied:true,changed:false,patch:'',error:''},
   {id:2,name:'write_solution',status:'failed',before:source,after:source,attemptedSource:'<script>bad</script>',applied:false,changed:false,patch:'',error:'rejected'},
   {id:3,name:'run_tests',status:'completed',before:source,after:source,attemptedSource:null,applied:false,changed:false,patch:'',visiblePassed:2,visibleTotal:3,error:''}]},
 skillHistory:[{id:'baseline',kind:'baseline',before:'Initial Skill',after:'Initial Skill',changed:false,note:'Frozen baseline Skill'},
  {id:'P001',kind:'proposal',before:'Initial Skill',after:'Initial Skill',changed:false,note:'Not selected',validationScore:0},
  {id:'P002',kind:'proposal',before:'Initial Skill',after:'Check boundary cases.',changed:true,note:'Selection not completed',patch:'-Initial Skill\n+Check boundary cases.'},
  {id:'pending',kind:'pending',before:'Initial Skill',after:null,changed:false,note:'No frozen selection; no evolution outcome confirmed'}]});

test('failed and incomplete traces show real attempts, unchanged source and Skill proposals without claiming success',()=>{
 const data=validateChanges(fixture()),html=changesView({changes:data},{id:data.runId});
 for(const text of ['未完成／中斷；無最終分數','寫入相同程式・未改變','未套用這次寫入','公開測試 2/3','本文未修改','修正後 Skill','沒有提案時不補造修改紀錄','歷程快照・不代表整輪通過','尚無凍結的 candidate','凍結的任務說明'])assert.ok(html.includes(text),text);
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/0%/); // A recorded zero is not missing evidence.
});
test('source revision shows before, after and diff; another Run cannot inherit it',()=>{
 const data=fixture(),step=data.trace.steps[0];step.after='def clamp(value, lower, upper):\n    return upper\n';step.changed=true;step.patch='-    return value\n+    return upper\n';
 const html=changesView({changes:data},{id:data.runId});assert.match(html,/已套用程式修改/);assert.match(html,/實際 diff/);
 assert.doesNotMatch(changesView({changes:data},{id:'RUN-other'}),/Initial Skill|PY-boundary/);
});
test('source history validation rejects foreign identities, oversized bodies and malformed tools',()=>{
 for(const modify of [d=>d.runId='../outside',d=>d.rollouts[0].id='../../outside',d=>d.trace.steps[0].name='exec',d=>d.trace.steps[0].after='a'.repeat(8001),d=>d.skillHistory[1].kind='verified-by-model',d=>d.historyOnly=false]){
  const data=fixture();modify(data);assert.throws(()=>validateChanges(data));
 }
});
test('read history uses one GET and preserves every execution setting and frozen pending request',async()=>{
 const calls=[],client=new RuntimeClient({fetcher:async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>fixture()};}});
 client.data={serviceId:'history-service'};client.pendingGepaSubmission={maxSeconds:1800,metricBudget:80};
 const pending=structuredClone(client.pendingGepaSubmission);
 assert.equal(await client.readChanges('RUN-history','R0001'),true);
 assert.equal(calls.length,1);assert.equal(calls[0].options.method,'GET');
 assert.match(calls[0].path,/debug\/changes\/RUN-history\?rollout=R0001&offset=0/);
 assert.deepEqual(client.pendingGepaSubmission,pending);assert.equal(client.gepaSeconds,1800);
});
test('out-of-order replies and responses from another Run or service cannot replace the selected history',async()=>{
 const waiting=[],client=new RuntimeClient({fetcher:async()=>new Promise(resolve=>waiting.push(resolve))});client.data={serviceId:'service-one'};
 const first=client.readChanges('RUN-first'),second=client.readChanges('RUN-second');
 waiting[1]({ok:true,json:async()=>fixture('RUN-second')});assert.equal(await second,true);
 waiting[0]({ok:true,json:async()=>fixture('RUN-first')});assert.equal(await first,false);assert.equal(client.changes.runId,'RUN-second');
 const third=client.readChanges('RUN-third');client.data={serviceId:'service-two'};
 waiting[2]({ok:true,json:async()=>fixture('RUN-third')});assert.equal(await third,false);assert.equal(client.changes.runId,'RUN-second');
 client.fetcher=async()=>({ok:true,json:async()=>fixture('RUN-wrong')});assert.equal(await client.readChanges('RUN-third'),false);assert.match(client.changeError,/不一致/);
});
test('profile presets count mandatory final runs and three verifier passes, while explicit caps stay frozen',()=>{
 const client=new RuntimeClient({fetcher:async()=>{throw Error('No HTTP');}});
 assert.deepEqual(gepaPlan(client),{search:8,final:12,rollouts:20,calls:162,verificationBatches:60,seconds:1800,full:false});
 client.pendingGepaSubmission={profile:'smoke',maxSeconds:1800};client.setGepaProfile('full');
 assert.deepEqual(gepaPlan(client),{search:26,final:60,rollouts:86,calls:689,verificationBatches:258,seconds:7200,full:true});
 assert.deepEqual(client.pendingGepaSubmission,{profile:'smoke',maxSeconds:1800});
 client.gepaMetrics=80;client.gepaProposals=4;client.gepaSeconds=1800;
 assert.equal(gepaPlan(client).calls,1124);assert.equal(gepaPlan(client).rollouts,140);
 assert.match(gepaView(client.snapshot()),/容易在取得最終成果前逾時/);
 assert.equal(client.gepaSeconds,1800); // Rendering cannot extend an explicit deadline.
 client.setGepaProfile('smoke');assert.equal(client.gepaSeconds,1800);assert.equal(client.gepaMetrics,8);
});
