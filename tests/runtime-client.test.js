import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateRuntime,telemetryLabel} from '../dist/js/runtime-client.js';
import {runtimeView} from '../dist/js/runtime-view.js';
import {initialRegistry} from '../dist/js/agents.js';
const stamp='2026-10-11T12:00:00Z';
const caps={schemaVersion:1,mode:'native-tools',serviceId:'service-test',csrfToken:'test-csrf-token-at-least-twenty-characters'};
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:caps.serviceId,serverTime:stamp,latestRun:null,runs:[]});
const running=()=>({...snapshot(),latestRun:{id:'RUN-test',requestId:'test',mode:'native-tools',status:'running',createdAt:stamp,updatedAt:stamp,checksPassed:null,agents:initialRegistry().agents.map((a,i)=>({...a,status:i?'queued':'running',adapter:'native-tool-agent',task:'actual check',pid:i?null:1234,processAlive:!i,startedAt:i?null:stamp,endedAt:null,updatedAt:stamp,exitCode:null,error:null,logTail:'tool output'})),events:[{at:stamp,agentId:'AG-001',text:'actual subprocess started'}],artifacts:[]},runs:[{id:'RUN-test',status:'running',createdAt:stamp}]});
const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});

test('polling reads capabilities once, then fresh snapshots with no-store',async()=>{
  const calls=[],client=new RuntimeClient({fetcher:async(path,options)=>{calls.push({path,options});return response(path.endsWith('capabilities')?caps:running());}});
  assert.equal(await client.refresh(),true);assert.equal(await client.refresh(),true);
  assert.equal(client.pollCount,2);assert.equal(calls.filter(c=>c.path.endsWith('capabilities')).length,1);
  assert.ok(calls.every(c=>c.options.cache==='no-store'));
  assert.equal(telemetryLabel(client.snapshot(),'AG-001'),'執行中');
});
test('a failed poll preserves last evidence and clearly marks stale status without demo fallback',async()=>{
  let fail=false;
  const client=new RuntimeClient({fetcher:async path=>{if(fail)throw Error('offline');return response(path.endsWith('capabilities')?caps:running());}});
  await client.refresh();const last=client.lastSuccess;fail=true;
  assert.equal(await client.refresh(),false);assert.equal(client.lastSuccess,last);assert.ok(client.data.latestRun);
  assert.equal(telemetryLabel(client.snapshot(),'AG-001'),'狀態過期');
  const html=runtimeView(client.snapshot());assert.match(html,/目前未確認/);assert.match(html,/快照過期/);
  assert.equal(client.capabilities,null);
});
test('overlapping refresh requests are skipped while the original request is in flight',async()=>{
  let unblock,count=0;
  const pending=new Promise(resolve=>unblock=resolve);
  const client=new RuntimeClient({fetcher:async path=>{count++;if(path.endsWith('capabilities')){await pending;return response(caps);}return response(snapshot());}});
  const first=client.refresh();assert.equal(await client.refresh(),false);assert.equal(count,1);
  unblock();assert.equal(await first,true);assert.equal(client.pollCount,1);
});
test('automatic polling repeats and stopping polling does not cancel server work',async()=>{
  const paths=[];
  const client=new RuntimeClient({interval:1000,fetcher:async path=>{paths.push(path);return response(path.endsWith('capabilities')?caps:running());}});
  try{await client.start();await new Promise(resolve=>setTimeout(resolve,1200));assert.ok(client.pollCount>=2);}finally{client.stop();}
  const count=client.pollCount;await new Promise(resolve=>setTimeout(resolve,100));assert.equal(client.pollCount,count);
  assert.ok(paths.every(p=>!p.endsWith('/cancel')));assert.equal(client.data.latestRun.status,'running');
  assert.throws(()=>client.setInterval(17));
});
test('real run and cancellation use the same-origin token and never mutate demo records',async()=>{
  const requests=[];let started=false;
  const client=new RuntimeClient({fetcher:async(path,options)=>{requests.push({path,options});if(path.endsWith('capabilities'))return response(caps);if(options.method==='POST'){started=true;return response({id:'RUN-test'});}return response(started?running():snapshot());}});
  const registry=initialRegistry(),before=structuredClone(registry);
  await client.refresh();await client.run(registry);await client.cancel('RUN-test');
  assert.deepEqual(registry,before);
  const mutations=requests.filter(r=>r.options.method==='POST');assert.equal(mutations.length,2);
  assert.ok(mutations.every(r=>r.options.headers['X-Lab-Token']===caps.csrfToken));
  assert.equal(JSON.parse(mutations[0].options.body).registry.agents.length,5);
  assert.ok(JSON.parse(mutations[0].options.body).requestId);
});
test('server restart and invalid snapshots invalidate capabilities instead of inventing states',async()=>{
  let data=running();
  const client=new RuntimeClient({fetcher:async path=>response(path.endsWith('capabilities')?caps:data)});
  await client.refresh();data={...running(),serviceId:'restarted'};
  assert.equal(await client.refresh(),false);assert.equal(client.capabilities,null);
  const invalid=running();invalid.latestRun.agents[0].status='simulated';assert.throws(()=>validateRuntime(invalid));
  const duplicate=running();duplicate.latestRun.agents[1].id=duplicate.latestRun.agents[0].id;assert.throws(()=>validateRuntime(duplicate));
  assert.throws(()=>validateRuntime({...snapshot(),runs:[null]}));
});
test('live output and connection errors are escaped and history states remain textual',()=>{
  const data=running(),payload='<img src=x onerror="alert(1)">';data.latestRun.agents[0].logTail=payload;
  const view={data,capabilities:caps,error:payload,lastSuccess:stamp,interval:2000,enabled:true,pollCount:3};
  const html=runtimeView(view);assert.equal(html.includes(payload),false);assert.match(html,/&lt;img/);
});
