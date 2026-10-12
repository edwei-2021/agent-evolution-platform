import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateRuntime} from '../dist/js/runtime-client.js';
import {warmupView} from '../dist/js/warmup-view.js';
const stamp='2026-10-12T02:00:00Z';
const provider=()=>({revision:4,config:{model:'qwen3-coder:30b',inferenceTimeout:600},busy:true,warmup:{id:'WARM-test',revision:4,config:{model:'qwen3-coder:30b'},status:'RUNNING',startedAt:stamp,elapsedSeconds:80,timeoutSeconds:600}});
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:'warm-service',serverTime:stamp,runs:[],latestRun:null,provider:provider()});
const response=value=>({ok:true,status:200,json:async()=>value});
test('warmup uses a separate explicit POST with saved revision and no inference retry',async()=>{
 const calls=[],client=new RuntimeClient({fetcher:async(path,options)=>{calls.push({path,options});return response(path.endsWith('capabilities')?{schemaVersion:1,mode:'native-tools',serviceId:'warm-service',csrfToken:'valid-local-session-token'}:path==='/api/v1/llm/ollama'?provider():path.endsWith('/warmup')?provider().warmup:snapshot());}});
 await client.refresh();assert.equal(calls.some(c=>c.options.method==='POST'),false);
 await client.warmModel();const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,1);
 assert.equal(posts[0].path,'/api/v1/llm/ollama/warmup');assert.deepEqual(JSON.parse(posts[0].options.body),{expectedRevision:4,keepAliveMinutes:15});
 assert.equal(posts[0].options.headers['X-Lab-Token'],'valid-local-session-token');assert.equal(client.actionBusy,false);
 let failedPosts=0;client.fetcher=async(path,options)=>{if(options.method==='POST'){failedPosts++;throw Error('lost response');}return response(provider());};await assert.rejects(client.warmModel());assert.equal(client.actionBusy,false);assert.equal(failedPosts,1);
});
test('warmup progress distinguishes a past preload result from current residency and stale settings',()=>{
 const p=provider();let html=warmupView(p);assert.match(html,/已用 80 秒／上限 600 秒/);assert.match(html,/aria-label="等待模型暖機完成"/);assert.match(html,/data-model-warmup[^>]*disabled/);
 p.busy=false;Object.assign(p.warmup,{status:'PRELOAD_PASS',loadDurationMs:3200,elapsedMs:5000,finishedAt:stamp});
 html=warmupView(p);assert.match(html,/暖機成功紀錄/);assert.match(html,/仍可能卸載模型/);assert.match(html,/載入 3200 ms/);assert.doesNotMatch(html,/class="model-wait"/);
 p.revision=5;html=warmupView(p);assert.match(html,/先前模型設定/);
 html=warmupView(provider(),{stale:true});assert.doesNotMatch(html,/class="model-wait"/);assert.match(html,/紀錄過期/);
});
test('runtime validates warmup state and rejects invented ready status',()=>{
 assert.equal(validateRuntime(snapshot()).provider.warmup.status,'RUNNING');
 for(const mutate of [s=>s.provider.warmup.status='READY_FOREVER',s=>s.provider.warmup.elapsedSeconds='fast',s=>s.provider.busy='yes']){const s=snapshot();mutate(s);assert.throws(()=>validateRuntime(s));}
});
