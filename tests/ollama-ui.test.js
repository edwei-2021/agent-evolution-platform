import test from 'node:test';
import assert from 'node:assert/strict';
import {OllamaUI,ollamaView} from '../dist/js/ollama-ui.js';

const data=()=>({schemaVersion:1,revision:1,config:{host:'',port:11435,model:'test:local',metadataTimeout:10,inferenceTimeout:600,maxTokens:256},openaiBaseUrl:'http://172.22.160.1:11435/v1',nativeBaseUrl:'http://172.22.160.1:11435',historicalEvidence:{observedAt:'2026-10-11T22:35:51+08:00',serverVersion:'0.40.2',modelIds:['test:local'],openaiBaseUrl:'http://172.22.160.1:11435/v1'},latest:null});
const response=value=>({ok:true,json:async()=>value});
test('initialization and reading settings never request metadata or inference',async()=>{
 const calls=[];const ui=new OllamaUI({fetcher:async(path,options)=>{calls.push({path,options});return response(data());}});
 assert.equal(calls.length,0);await ui.operate('reload');
 assert.deepEqual(calls.map(c=>c.path),['/api/v1/llm/ollama']);assert.equal(calls[0].options.method,'GET');
 assert.match(ui.view(),/API 連通成功，推論尚未測試/);assert.match(ui.view(),/11435/);assert.match(ui.view(),/規則引擎/);
});
test('explicit chat pins revision and model config with a long inference wait and no automatic retry',async()=>{
 const calls=[];const ui=new OllamaUI({token:()=> 'test-token',fetcher:async(path,options)=>{calls.push({path,options});return response(path.endsWith('/chat')?{status:'INFERENCE_PASS'}:data());}});
 await ui.operate('reload');ui.prompt='OK';await ui.operate('chat');
 const call=calls.find(c=>c.path.endsWith('/chat'));assert.equal(call.options.headers['X-Lab-Token'],'test-token');
 assert.deepEqual(JSON.parse(call.options.body),{expectedRevision:1,prompt:'OK'});assert.equal(ui.busy,false);
 const failing=new OllamaUI({fetcher:async()=>{throw Error('offline');}});await assert.rejects(failing.operate('reload'),/offline/);assert.equal(failing.busy,false);
});
test('busy operations reject additional clicks and view escapes model output and marks prior settings',async()=>{
 const ui=new OllamaUI();ui.busy=true;await assert.rejects(ui.operate('chat'),/正在處理/);
 const value=data();value.latest={revision:0,endpoint:value.nativeBaseUrl,status:'INFERENCE_PASS',content:'<img src=x onerror=alert(1)>',elapsedMs:10,reportPath:'.local/report.json'};
 const html=ollamaView({data:value,error:null,busy:false,prompt:'<script>alert(1)</script>'});
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('<script>'));assert.match(html,/先前設定/);assert.match(html,/&lt;img/);
});
test('backend failure remains visible and only one explicit inference request is sent',async()=>{
 let posts=0;const ui=new OllamaUI({fetcher:async(path,options)=>{
  if(options.method==='POST'){posts++;return response({status:'FAIL',error:'model failed'});}
  return response(data());
 }});
 await ui.operate('reload');await assert.rejects(ui.operate('chat'),/model failed/);
 assert.equal(posts,1);assert.equal(ui.error,'model failed');assert.equal(ui.busy,false);
});
