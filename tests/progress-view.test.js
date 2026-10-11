import test from 'node:test';
import assert from 'node:assert/strict';
import {runProgressView,completedCalls} from '../dist/js/progress-view.js';
import {llmView} from '../dist/js/llm-view.js';
import {skillView} from '../dist/js/skill-view.js';
import {runtimeView} from '../dist/js/runtime-view.js';
const stamp='2026-10-11T18:00:00Z',epoch=Date.parse(stamp)/1000;
const run=()=>({id:'RUN-progress',task:'llm-evolution',status:'running',createdAt:stamp,updatedAt:stamp,
 agents:['coordinator','worker','reflector','evaluator','reviewer'].map((role,i)=>({id:`AG-${i}`,name:role,role,status:i===0?'completed':i===1?'running':'queued',pid:i===1?123:null,processAlive:i===1,updatedAt:stamp,logTail:''})),events:[],artifacts:[],
 llmConfig:{callBudget:15,maxSeconds:900,callTimeoutSeconds:120,baseline:{skill:{body:'Return input.'}},provider:{config:{model:'mock:1',inferenceTimeout:600},revision:1}},
 llmProgress:{calls:1,completedCalls:0,failedCalls:0,candidates:[],lastCall:{id:1,kind:'task',split:'train',taskId:'TR-01',status:'running',startedAt:epoch,deadlineEpoch:epoch+120,timeoutSeconds:120,chunks:0}}});
const view=r=>({data:{serverTime:'2026-10-11T18:00:40Z',latestRun:r,runs:[],llm:{latestRun:r,versions:[],active:{skill:{body:'Return input.'}}}},lastSuccess:'2026-10-11T18:00:40Z',enabled:true,capabilities:{},interval:2000,pollCount:20});
test('first request shows zero completed, real stages, waiting time and bounded remaining time',()=>{
 const r=run(),html=runProgressView(view(r),r);
 assert.match(html,/<strong>0 \/ 15<\/strong>/);assert.match(html,/<strong>1 \/ 5<\/strong>/);
 assert.match(html,/已送出 1 次/);assert.match(html,/本次已用 40 秒/);assert.match(html,/剩餘 80 秒/);
 assert.match(html,/等待模型首段回應/);assert.match(html,/等待較久/);
 assert.match(html,/<progress class="model-wait" aria-label="等待模型回應"><\/progress>/);
});
test('streamed text reports observed characters and last response without revealing partial output',()=>{
 const r=run();Object.assign(r.llmProgress.lastCall,{chunks:3,outputChars:17,reasoningChars:24,lastChunkAt:epoch+30});
 const html=runProgressView(view(r),r);
 assert.match(html,/已收到 3 段回應/);assert.match(html,/答案 17 字元/);assert.match(html,/reasoning 24 字元/);
 assert.match(html,/2026-10-11T18:00:30.000Z/);assert.doesNotMatch(html,/剩餘 120 秒/);
});
test('stale or paused polling removes live animations and keeps measured counts',()=>{
 const r=run();for(const extra of [{error:'offline'},{enabled:false}]){
  const html=runProgressView({...view(r),...extra},r);
  assert.match(html,/快照過期/);assert.match(html,/不代表後端已停止/);
  assert.doesNotMatch(html,/class="progress-spinner"|class="model-wait"/);assert.match(html,/<strong>0 \/ 15<\/strong>/);
 }
});
test('terminal runs freeze elapsed time, allow unused budget and surface escaped failures',()=>{
 const r=run();r.status='completed';r.endedAt='2026-10-11T18:00:25Z';r.agents.forEach(a=>a.status='completed');
 Object.assign(r.llmProgress,{calls:13,completedCalls:13});Object.assign(r.llmProgress.lastCall,{id:13,status:'completed',finishedAt:epoch+25});
 let html=runProgressView(view(r),r);assert.match(html,/整輪已用 25 秒/);assert.match(html,/<strong>13 \/ 15<\/strong>/);assert.match(html,/可以不必全部用完/);assert.doesNotMatch(html,/progress-spinner/);
 r.status='failed';r.error='<script>failure</script>';r.llmProgress.lastCall.status='failed';
 html=runProgressView(view(r),r);assert.match(html,/role="alert"/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 r.status='cancelled';html=runProgressView(view(r),r);assert.match(html,/不再送出後續模型請求/);
});
test('LLM, rule skill and runtime pages each render an accessible progress panel',()=>{
 const r=run(),runtime=view(r);
 assert.match(llmView(runtime),/data-execution-progress/);assert.match(runtimeView(runtime),/data-execution-progress/);
 const rules={...runtime,data:{...runtime.data,skills:null}};
 assert.match(skillView(rules),/data-execution-progress/);
 assert.match(runProgressView(runtime,null),/<progress value="0" max="5"/);
});
test('older progress snapshots count the unfinished request conservatively',()=>{
 for(const status of ['running','failed','cancelled'])assert.equal(completedCalls({calls:1,lastCall:{status}}),0);
 assert.equal(completedCalls({calls:13,lastCall:{status:'completed'}}),13);
});
