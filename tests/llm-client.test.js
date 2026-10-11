import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateLlmWorkspace,validateLlmRun} from '../dist/js/runtime-client.js';
import {llmView} from '../dist/js/llm-view.js';
import {initialRegistry} from '../dist/js/agents.js';
const stamp='2026-10-11T15:00:00Z',hash='a'.repeat(64);
const caps={schemaVersion:1,mode:'native-tools',serviceId:'llm-service',csrfToken:'at-least-twenty-characters-test-token'};
const skill=()=>({name:'normalize-support-title',description:'Normalize titles.',body:'Return input unchanged.',hash});
const metric=(passed,total)=>({passed,total,score:passed/total,loss:total-passed});
const version=()=>({id:'LSV-baseline',label:'L0',skill:skill(),createdAt:stamp,runId:null});
const workspace=()=>({schemaVersion:1,engine:'ollama-prompt-reflection-v1',revision:1,activeVersionId:'LSV-baseline',active:version(),versions:[version()],runs:[],latestRun:null});
const run=()=>({id:'RUN-llm',requestId:'request',task:'llm-evolution',mode:'native-tools',status:'completed',createdAt:stamp,updatedAt:stamp,
 agents:initialRegistry().agents.map(a=>({...a,status:'completed',pid:1234,processAlive:false,updatedAt:stamp,logTail:'model output'})),events:[],artifacts:['llm-calls.json','review.json'],
 llmConfig:{profile:'smoke',baseline:version(),callBudget:15,maxSeconds:900,maxOutputTokens:3840,provider:{revision:1,config:{model:'mock:local'},endpoint:'http://127.0.0.1:11435'}},
 llmProgress:{engine:'ollama-prompt-reflection-v1',phase:'reviewer',calls:15,trainingFailures:[],candidates:[{id:'C0',skill:skill(),training:metric(0,3),validation:metric(0,2)},{id:'C1',skill:{...skill(),body:'Normalize input.'},training:metric(3,3),validation:metric(2,2)}]},
 llmResult:{eligible:true,decision:'ready-for-human-review',selectedSkill:skill(),selectedValidation:metric(2,2),heldout:{baseline:metric(0,2),selected:metric(2,2)}}});
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:caps.serviceId,serverTime:stamp,latestRun:null,runs:[],llm:workspace()});
const view=(data=snapshot(),extra={})=>({data,capabilities:caps,error:null,lastSuccess:stamp,pollCount:3,interval:2000,enabled:true,actionBusy:false,llmProfile:'smoke',llmSeconds:900,...extra});
const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});

test('model workspace validates separate prompt versions, budgets and actual score denominators',()=>{
 assert.equal(validateLlmWorkspace(workspace()).engine,'ollama-prompt-reflection-v1');assert.equal(validateLlmRun(run()).task,'llm-evolution');
 for(const mutate of [v=>v.activeVersionId='LSV-missing',v=>v.versions.push(version()),v=>v.revision=true]){const w=workspace();mutate(w);assert.throws(()=>validateLlmWorkspace(w));}
 const r=run();r.llmProgress.calls=16;assert.throws(()=>validateLlmRun(r));
 r.llmProgress.calls=15;r.llmResult.selectedValidation.score=.99;assert.throws(()=>validateLlmRun(r));
});
test('model approval is gated on current complete evidence and unchanged baseline',()=>{
 const data=snapshot();data.llm.latestRun=run();
 const approval=html=>html.match(/<button[^>]*data-llm-approve[^>]*>/)[0];
 assert.equal(approval(llmView(view(data))).includes('disabled'),false);
 for(const extra of [{error:'offline'},{actionBusy:true}])assert.ok(approval(llmView(view(data,extra))).includes('disabled'));
 data.llm.latestRun.status='cancelled';assert.ok(approval(llmView(view(data))).includes('disabled'));
 data.llm.latestRun.status='completed';data.llm.activeVersionId='LSV-new';assert.ok(approval(llmView(view(data))).includes('disabled'));
});
test('model output and body are escaped; disconnected view does not invent scores',()=>{
 const data=snapshot();data.llm.latestRun=run();const payload='<img src=x onerror=alert(1)>';
 data.llm.latestRun.llmProgress.candidates[1].skill.body=payload;
 data.llm.latestRun.llmProgress.trainingFailures=[{taskId:'TR-01',input:payload,output:payload,expected:'expected'}];
 const html=llmView(view(data));assert.ok(!html.includes(payload));assert.match(html,/&lt;img/);assert.match(html,/15 次模型呼叫/);assert.match(html,/未接入 nanobot／GEPA/);
 const offline=llmView(view(null,{error:'offline'}));assert.match(offline,/尚未評估/);assert.match(offline,/<button[^>]*data-llm-start[^>]*disabled/);
});
test('LLM submit reads local provider settings and pins revisions without metadata probes',async()=>{
 const calls=[];const client=new RuntimeClient({fetcher:async(path,options)=>{
  calls.push({path,options});
  if(path.endsWith('capabilities'))return response(caps);
  if(path==='/api/v1/llm/ollama')return response({revision:7});
  if(options.method==='POST')return response({});
  return response(snapshot());
 }});
 await client.refresh();await client.startLlm(initialRegistry());await client.approveLlm('RUN-llm');await client.activateLlm('LSV-baseline');
 const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,3);
 const body=JSON.parse(posts[0].options.body);assert.equal(body.providerRevision,7);assert.equal(body.expectedRevision,1);assert.equal(body.profile,'smoke');assert.equal(body.maxSeconds,900);assert.equal(body.callTimeoutSeconds,120);
 assert.ok(posts.every(c=>c.options.headers['X-Lab-Token']===caps.csrfToken));assert.ok(!calls.some(c=>c.path.endsWith('/metadata')||c.path.endsWith('/chat')));
});
test('uncertain LLM submission retains the same request body and never auto-retries',async()=>{
 const bodies=[];let fail=true;
 const client=new RuntimeClient({fetcher:async(path,options)=>{
  if(path.endsWith('capabilities'))return response(caps);
  if(path==='/api/v1/llm/ollama')return response({revision:1});
  if(options.method==='POST'){bodies.push(JSON.parse(options.body));if(fail)throw Error('lost response');return response({});}
  return response(snapshot());
 }});
 await client.refresh();await assert.rejects(client.startLlm(initialRegistry()));assert.equal(bodies.length,1);
 client.llmProfile='full';client.llmCallSeconds=360;fail=false;await client.startLlm(initialRegistry());assert.deepEqual(bodies[0],bodies[1]);assert.equal(client.pendingLlmSubmission,null);
});
test('model telemetry rejects impossible completion counts and invalid timing',()=>{
 for(const changes of [{completedCalls:16},{completedCalls:14,failedCalls:2},{failedCalls:-1},{lastCall:{id:1,status:'running',startedAt:'fake'}}]){
  const r=run();Object.assign(r.llmProgress,changes);assert.throws(()=>validateLlmRun(r));
 }
});
