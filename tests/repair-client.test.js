import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateRepairRun,validateRepairWorkspace} from '../dist/js/runtime-client.js';
import {repairView} from '../dist/js/repair-view.js';
import {initialRegistry} from '../dist/js/agents.js';
const stamp='2026-10-12T03:00:00Z';
const caps={schemaVersion:1,mode:'native-tools',serviceId:'repair-service',csrfToken:'valid-local-session-token'};
const sdk=()=>({available:true,version:'0.3.5',requiredVersion:'0.3.5',error:null});
const result=()=>({repairPassed:true,sdkVersion:'0.3.5',evidenceHash:'a'.repeat(64),baseline:{visible:{passed:3,total:6},hidden:{passed:1,total:6}},candidate:{visible:{passed:6,total:6},hidden:{passed:6,total:6}}});
const run=()=>({id:'RUN-repair',task:'nanobot-repair',mode:'native-tools',status:'completed',createdAt:stamp,updatedAt:stamp,endedAt:stamp,events:[],artifacts:['repair-candidate.py','repair-change.patch'],agents:initialRegistry().agents.map(a=>({...a,status:'completed',pid:123,processAlive:false,updatedAt:stamp,logTail:''})),
 repairConfig:{engine:'nanobot-python-repair-v1',sdk:sdk(),skill:{name:'python-fix-and-verify'},callBudget:8,maxSeconds:900,provider:{config:{model:'qwen3-coder:30b',inferenceTimeout:600}}},repairProgress:{engine:'nanobot-python-repair-v1',phase:'reviewer',calls:4,completedCalls:4,failedCalls:0,toolCalls:3},repairResult:result()});
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:caps.serviceId,serverTime:stamp,runs:[],latestRun:null,repair:{engine:'nanobot-python-repair-v1',sdk:sdk(),latestRun:null,runs:[]}});
const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});
test('repair workspace validates actual fixture denominators and accepts code/patch artifacts',()=>{
 assert.equal(validateRepairRun(run()).task,'nanobot-repair');assert.equal(validateRepairWorkspace(snapshot().repair).sdk.version,'0.3.5');
 for(const mutate of [r=>r.repairConfig.callBudget=99,r=>r.repairProgress.calls=9,r=>r.repairResult.candidate.hidden.total=500,r=>r.repairConfig.sdk.version='latest',r=>r.repairProgress.lastCall={id:'<img>',status:'running'},r=>r.repairResult.candidate.hidden.passed=0]){const r=run();mutate(r);assert.throws(()=>validateRepairRun(r));}
});
test('SDK availability, model activity and stale snapshots gate repair start',()=>{
 const runtime={data:snapshot(),capabilities:caps,enabled:true,error:null,repairBudget:8};
 const button=html=>html.match(/<button[^>]*data-repair-start[^>]*>/)[0];
 assert.ok(!button(repairView(runtime)).includes('disabled'));
 for(const modify of [r=>r.error='offline',r=>r.data.repair.sdk.available=false,r=>r.data.provider={busy:true},r=>r.data.latestRun={status:'running'}]){const r=structuredClone(runtime);modify(r);assert.match(button(repairView(r)),/disabled/);}
});
test('repair submit freezes saved model revision and retains immutable uncertain request without retrying',async()=>{
 const bodies=[];let fail=true;
 const client=new RuntimeClient({fetcher:async(path,options)=>{
  if(path.endsWith('/capabilities'))return response(caps);
  if(path==='/api/v1/llm/ollama')return response({revision:7});
  if(options.method==='POST'){bodies.push(JSON.parse(options.body));if(fail)throw Error('lost response');return response({});}
  return response(snapshot());
 }});
 await client.refresh();await assert.rejects(client.startRepair(initialRegistry()));assert.equal(bodies.length,1);
 assert.equal(bodies[0].providerRevision,7);assert.equal(bodies[0].callBudget,8);assert.equal(bodies[0].callTimeoutSeconds,120);
 client.repairBudget=12;fail=false;await client.startRepair(initialRegistry());assert.deepEqual(bodies[0],bodies[1]);assert.equal(client.pendingRepairSubmission,null);
});
test('read-only repair evidence previews retain artifact boundaries and escaped trace output',async()=>{
 const payload='<script>bad</script>';let truncated=false;
 const client=new RuntimeClient({fetcher:async path=>response({content:path.endsWith('repair-tools.json')?JSON.stringify([{id:1,name:'read_solution',status:'completed',result:payload}]):payload,truncated})});
 await client.readRepairEvidence('RUN-repair');assert.equal(client.repairEvidence.patch,payload);
 const data=snapshot();data.repair.latestRun=run();const html=repairView({...client.snapshot(),data,capabilities:caps,enabled:true});
 assert.ok(!html.includes(payload));assert.match(html,/&lt;script&gt;/);assert.match(html,/6 \/ 6/);assert.match(html,/data-execution-progress/);assert.match(html,/不建立新 Skill 版本/);
 truncated=true;await assert.rejects(client.readRepairEvidence('RUN-repair'),/預覽超限/);
});
