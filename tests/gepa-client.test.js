import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateGepaRun,validateGepaWorkspace} from '../dist/js/runtime-client.js';
import {gepaView} from '../dist/js/gepa-view.js';
import {initialRegistry} from '../dist/js/agents.js';
const stamp='2026-10-12T06:00:00Z';
const caps={schemaVersion:1,mode:'native-tools',serviceId:'gepa-service',csrfToken:'valid-local-session-token'};
const skill=(body='Read, repair, test.',hash='a')=>({name:'python-fix-and-verify',description:'Bounded repair.',body,hash:hash.repeat(64)});
const run=()=>({id:'RUN-gepa',task:'gepa-evolution',mode:'native-tools',status:'completed',createdAt:stamp,updatedAt:stamp,endedAt:stamp,events:[],artifacts:['gepa-selection.md'],agents:initialRegistry().agents.map(a=>({...a,status:'completed',pid:123,processAlive:false,updatedAt:stamp,logTail:''})),
 gepaConfig:{engine:'gepa-nanobot-repair-v1',sdk:{version:'0.3.5'},optimizer:{version:'0.1.4'},baseline:{id:'GSV-baseline',skill:skill()},profile:'smoke',callBudget:122,metricBudget:8,proposalBudget:2,counts:{train:4,validation:2,heldout:4},maxSeconds:1800,provider:{config:{model:'local-model',inferenceTimeout:120}}},
 gepaProgress:{engine:'gepa-nanobot-repair-v1',calls:40,completedCalls:40,failedCalls:0,metricEvaluations:6,proposals:1,rollouts:18},
 gepaResult:{engine:'gepa-nanobot-repair-v1',checksPassed:true,eligible:true,selectedSkill:skill('Repair with tests.','b'),baselineSkill:skill(),evidenceHash:'c'.repeat(64),calls:40,metricEvaluations:6,proposals:1,rollouts:18,final:{baseline:{validation:{passed:0,total:2},heldout:{passed:0,total:4}},selected:{validation:{passed:2,total:2},heldout:{passed:4,total:4}}}}});
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:caps.serviceId,serverTime:stamp,runs:[],latestRun:null,gepa:{schemaVersion:1,engine:'gepa-nanobot-repair-v1',revision:1,activeVersionId:'GSV-baseline',active:{id:'GSV-baseline',skill:skill()},versions:[{id:'GSV-baseline',label:'G0',skill:skill(),runId:null}],sdk:{available:true,version:'0.3.5'},optimizer:{available:true,version:'0.1.4'},latestRun:null,runs:[]}});
const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});
test('GEPA validates separate versions, score denominators, budgets and truthful release eligibility',()=>{
 assert.equal(validateGepaRun(run()).task,'gepa-evolution');assert.equal(validateGepaWorkspace(snapshot().gepa).activeVersionId,'GSV-baseline');
 for(const modify of [r=>r.gepaConfig.optimizer.version='latest',r=>r.gepaProgress.calls=200,r=>r.gepaProgress.metricEvaluations=9,r=>r.gepaResult.final.selected.heldout.total=50,r=>r.gepaResult.final.selected.validation.passed=0,r=>r.gepaResult.selectedSkill.name='mutated',r=>r.gepaProgress.lastCall={id:41,status:'running'}]){const r=run();modify(r);assert.throws(()=>validateGepaRun(r));}
});
test('GEPA availability, stale polling and shared model activity gate start while evidence is escaped',()=>{
 const runtime={data:snapshot(),capabilities:caps,enabled:true,error:null};const button=html=>html.match(/<button[^>]*data-gepa-start[^>]*>/)[0];
 assert.ok(!button(gepaView(runtime)).includes('disabled'));
 for(const modify of [r=>r.data.gepa.optimizer.available=false,r=>r.enabled=false,r=>r.error='stale',r=>r.data.provider={busy:true},r=>r.data.latestRun={status:'running'}]){const r=structuredClone(runtime);modify(r);assert.match(button(gepaView(r)),/disabled/);}
 runtime.data.gepa.latestRun=run();runtime.data.gepa.latestRun.gepaResult.selectedSkill.body='<script>alert(1)</script>';
 const html=gepaView(runtime);assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/data-execution-progress/);assert.match(html,/data-gepa-search-progress/);assert.match(html,/2 \/ 2/);assert.ok(!html.match(/data-gepa-approve[^>]*disabled/));
 runtime.data.gepa.activeVersionId='GSV-other';assert.match(gepaView(runtime),/data-gepa-approve[^>]*disabled/);
});
test('GEPA submits a frozen body on saved revisions and uncertain dispatch never automatically retries',async()=>{
 const posts=[];let fail=true;
 const client=new RuntimeClient({fetcher:async(path,options)=>{
  if(path.endsWith('/capabilities'))return response(caps);if(path==='/api/v1/llm/ollama')return response({revision:7});
  if(options.method==='POST'){posts.push(JSON.parse(options.body));if(fail)throw Error('lost response');return response({});}
  return response(snapshot());
 }});
 await client.refresh();await assert.rejects(client.startGepa(initialRegistry()));assert.equal(posts.length,1);assert.equal(posts[0].providerRevision,7);assert.equal(posts[0].expectedRevision,1);
 client.gepaMetrics=80;fail=false;await client.startGepa(initialRegistry());assert.deepEqual(posts[1],posts[0]);assert.equal(client.pendingGepaSubmission,null);
});
test('GEPA version actions use their own revisions and definitive rejection permits corrected submission',async()=>{
 const calls=[];let reject=true;
 const client=new RuntimeClient({fetcher:async(path,options)=>{
  calls.push({path,options});if(path.endsWith('/capabilities'))return response(caps);if(path==='/api/v1/llm/ollama')return response({revision:7});
  if(path==='/api/v1/gepa/runs'&&reject)return {ok:false,status:400,json:async()=>({error:'bad budget'})};return response(snapshot());
 }});
 await client.refresh();await assert.rejects(client.startGepa(initialRegistry()),/bad budget/);assert.equal(client.pendingGepaSubmission,null);
 reject=false;client.gepaMetrics=6;await client.startGepa(initialRegistry());await client.approveGepa('RUN-gepa');await client.activateGepa('GSV-baseline');
 assert.deepEqual(JSON.parse(calls.find(c=>c.path.endsWith('/approve')).options.body),{expectedRevision:1});assert.ok(calls.some(c=>c.path==='/api/v1/gepa/versions/GSV-baseline/activate'));
});
