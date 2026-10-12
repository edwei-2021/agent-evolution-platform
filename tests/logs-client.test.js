import test from 'node:test';
import assert from 'node:assert/strict';
import {LogsClient,validateLogs} from '../dist/js/logs-client.js';
import {logsView,logsResultsView} from '../dist/js/logs-view.js';
const stamp='2026-10-12T02:00:00Z';
const row=id=>({id,at:stamp,module:'llm',level:'ERROR',runId:'RUN-debug',message:`call ${id} failed`,details:{timeoutSeconds:120}});
const page=(ids=[3,2],next=2)=>({schemaVersion:1,records:ids.map(row),retained:3,matched:3,retentionLimit:10000,nextBefore:next,modules:['llm','api','gui'],levels:['ERROR','INFO'],serverTime:stamp});
test('log filters encode query values and pagination preserves measured IDs without duplicate dispatch',async()=>{
 const paths=[];const client=new LogsClient({request:async path=>{paths.push(path);return paths.length===1?page():page([1],null);}});
 await client.filter({module:'llm',level:'ERROR',runId:'RUN-debug',q:'timeout & model'});
 const query=new URL('http://localhost'+paths[0]).searchParams;
 assert.equal(query.get('q'),'timeout & model');assert.equal(query.get('module'),'llm');
 await client.refresh(true);assert.match(paths[1],/before=2/);assert.deepEqual(client.data.records.map(r=>r.id),[3,2,1]);assert.equal(client.enabled,false);
 const exported=client.export().trim().split('\n').map(JSON.parse);assert.deepEqual(exported,client.data.records);
});
test('an older response cannot overwrite a changed filter and failed polling preserves evidence',async()=>{
 let resolveOld;let count=0;
 const client=new LogsClient({request:async()=>{count++;if(count===1)return new Promise(r=>resolveOld=r);if(count===2)return page([8],null);throw Error('offline');}});
 const old=client.refresh();await client.filter({module:'api'});resolveOld(page());await old;
 assert.equal(client.filters.module,'api');assert.equal(client.data.records[0].id,8);
 assert.equal(await client.refresh(),false);assert.equal(client.data.records[0].id,8);assert.equal(client.error,'offline');
});
test('log rendering escapes all output, shows local time, freshness and bounded export scope',()=>{
 const payload='<img src=x onerror=alert(1)>',client=new LogsClient({request:async()=>page()});
 client.data=page([1],null);client.data.records[0].message=payload;client.data.records[0].details.error=payload;client.error=payload;
 const html=logsView(client.snapshot(),{data:{runs:[]}});
 assert.ok(!html.includes(payload));assert.match(html,/&lt;img/);assert.match(html,/Asia\/Taipei/);assert.match(html,/保留上次紀錄/);
 assert.match(html,/匯出目前 JSONL/);assert.match(html,/Windows Ollama server.log/);
});
test('invalid metadata, invented levels, duplicate IDs and broken cursors are rejected',()=>{
 for(const mutate of [p=>p.records[0].level='OK',p=>p.records.push(row(2)),p=>p.nextBefore=999,p=>p.modules.push('" onclick="bad')]){
  const p=page();mutate(p);assert.throws(()=>validateLogs(p));
 }
});
test('raw role selection ignores obsolete responses and renders failures without replacing retained content',async()=>{
 let release;const client=new LogsClient({request:async()=>new Promise(r=>release=r)});
 client.selectRawRun('RUN-old');const old=client.readRole('worker');client.selectRawRun('RUN-new');
 release({runId:'RUN-old',role:'worker',content:'old',truncated:false});await old;assert.equal(client.raw,null);
 client.request=async()=>({runId:'RUN-new',role:'worker',content:'<script>bad</script>',truncated:true});await client.readRole('worker');
 const html=logsResultsView(client.snapshot());assert.match(html,/&lt;script&gt;/);assert.match(html,/最後 200,000 bytes/);
 client.request=async()=>{throw Error('not available');};assert.equal(await client.readRole('reviewer'),false);assert.equal(client.raw.role,'worker');
});
