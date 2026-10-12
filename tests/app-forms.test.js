import test from 'node:test';
import assert from 'node:assert/strict';

// Run the real app event listeners without a browser dependency. Model the
// connected-form rule: replacing #main detaches its form before default submit.
test('app form events preserve settings through click, submit, navigation and LLM start',async t=>{
 const names=['document','window','location','history','FormData','fetch','setTimeout','clearTimeout','setInterval','clearInterval'];
 const originals=new Map(names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
 t.after(()=>{for(const [name,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];}});
 const listeners=new Map(),windowListeners=new Map(),forms=new Set(),calls=[];
 const node=()=>({textContent:'',dataset:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},addEventListener(){}});
 const main=node();let html='',renders=0;
 Object.defineProperty(main,'innerHTML',{get:()=>html,set:value=>{html=value;renders++;for(const form of forms)form.isConnected=false;}});
 const nodes=new Map([['#main',main]]);
 const add=(map,type,handler)=>map.set(type,[...(map.get(type)||[]),handler]);
 const dispatch=async(type,event)=>{for(const handler of listeners.get(type)||[])await handler(event);};
 globalThis.document={activeElement:null,addEventListener:(type,handler)=>add(listeners,type,handler),querySelector:selector=>{
  if(selector==='dialog[open]')return null;
  if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);
 },querySelectorAll:()=>[]};
 globalThis.window={localStorage:{getItem:()=>null,setItem(){}},addEventListener:(type,handler)=>add(windowListeners,type,handler)};
 globalThis.location={hash:'#integrations'};globalThis.history={replaceState(){}};
 globalThis.FormData=class extends Map{constructor(form){super(Object.entries(form.fields));}};
 globalThis.setTimeout=globalThis.setInterval=()=>1;globalThis.clearTimeout=globalThis.clearInterval=()=>{};
 const stamp='2026-10-11T15:00:00Z',skill={name:'normalize-support-title',description:'Normalize titles.',body:'Return input unchanged.',hash:'a'.repeat(64)};
 const version={id:'LSV-baseline',label:'L0',skill,createdAt:stamp,runId:null};
 const runtime={schemaVersion:1,mode:'native-tools',serviceId:'forms-service',serverTime:stamp,runs:[],latestRun:null,
  llm:{schemaVersion:1,engine:'ollama-prompt-reflection-v1',revision:1,activeVersionId:version.id,active:version,versions:[version],runs:[],latestRun:null}};
 let saved={schemaVersion:1,revision:0,config:{host:'',port:11435,model:'',metadataTimeout:10,inferenceTimeout:600,maxTokens:256},nativeBaseUrl:'http://127.0.0.1:11435',openaiBaseUrl:'http://127.0.0.1:11435/v1',historicalEvidence:{modelIds:['qwen3-coder:30b']},latest:null};
 let failure=false;
 globalThis.fetch=async(path,options)=>{
  calls.push({path,options});let value,ok=true;
  if(path.endsWith('/capabilities'))value={schemaVersion:1,mode:'native-tools',serviceId:runtime.serviceId,csrfToken:'a-valid-local-session-token'};
  else if(path==='/api/v1/runtime')value=runtime;
  else if(path==='/api/v1/llm/ollama')value=saved;
  else if(path.startsWith('/api/v1/debug/logs?'))value={schemaVersion:1,records:[],retained:0,matched:0,retentionLimit:10000,nextBefore:null,modules:['api','gui','llm'],levels:['DEBUG','INFO','WARNING','ERROR']};
  else if(path==='/api/v1/llm/ollama/warmup'){
   const body=JSON.parse(options.body);assert.equal(body.expectedRevision,saved.revision);
   value={id:'WARM-forms',revision:saved.revision,status:'RUNNING',startedAt:stamp,elapsedSeconds:0,timeoutSeconds:600,config:saved.config};
   runtime.provider={revision:saved.revision,config:saved.config,busy:true,warmup:value};
  }
  else if(path.endsWith('/settings')){
   const body=JSON.parse(options.body);
   if(failure){ok=false;value={error:'Settings revision conflict'};}
   else{assert.equal(body.expectedRevision,saved.revision);saved={...saved,revision:saved.revision+1,config:body.config};value=saved;}
  }else if(path.endsWith('/runs'))value={};
  else throw Error(`Unexpected request: ${path}`);
  return {ok,status:ok?200:409,json:async()=>structuredClone(value)};
 };
 await import(`../dist/js/app.js?forms-regression=${Date.now()}`);
 // Flush initialization's independent local settings and runtime reads.
 for(let i=0;i<20;i++)await Promise.resolve();
 const form=(id,fields)=>{const value={id,fields,isConnected:true};forms.add(value);return value;};
 const button=(form=null,dataset={},type=form?'submit':'button')=>({form,type,dataset,closest:selector=>selector==='button'?buttonValue:null,hasAttribute:name=>Object.hasOwn(dataset,name.replace(/^data-/,'').replace(/-([a-z])/g,(_,c)=>c.toUpperCase()))});
 let buttonValue;
 const click=async value=>{buttonValue=value;await dispatch('click',{target:value});};
 const submit=async value=>{
  assert.equal(value.isConnected,true,'click must keep the form connected until submit');
  let prevented=false;await dispatch('submit',{target:value,preventDefault(){prevented=true;}});assert.equal(prevented,true);
 };
 await t.test('clicking Save keeps the form connected and posts the typed model exactly once',async()=>{
  const fields={...saved.config,model:'qwen3-coder:30b'};
  const settings=form('ollama-settings-form',fields),before=renders;
  await click(button(settings));assert.equal(renders,before);await submit(settings);
  assert.equal(saved.config.model,'qwen3-coder:30b');assert.match(html,/value="qwen3-coder:30b"/);
  assert.equal(calls.filter(c=>c.path.endsWith('/settings')).length,1);
 });
 await t.test('Enter submit saves numeric settings and page navigation retains the model for LLM start',async()=>{
  await submit(form('ollama-settings-form',{...saved.config,maxTokens:'512'}));
  assert.equal(saved.config.maxTokens,512);
  await click(button(null,{page:'llm'}));await click(button(null,{llmStart:''}));
  const start=calls.find(c=>c.path==='/api/v1/llm/skills/runs');assert.ok(start);
  assert.equal(JSON.parse(start.options.body).providerRevision,saved.revision);
  await click(button(null,{page:'integrations'}));assert.match(html,/value="qwen3-coder:30b"/);
  assert.ok(!calls.some(c=>c.path.endsWith('/metadata')||c.path.endsWith('/chat')));
 });
 await t.test('failed save keeps every typed field for correction without a success message',async()=>{
  failure=true;await submit(form('ollama-settings-form',{...saved.config,model:'qwen3:30b',inferenceTimeout:'750'}));
  assert.equal(saved.config.model,'qwen3-coder:30b');assert.match(html,/value="qwen3:30b"/);assert.match(html,/value="750"/);
  assert.match(html,/Settings revision conflict/);assert.equal(nodes.get('#toast').textContent,'Settings revision conflict');
 });
 await t.test('chat, trial and dialog submit buttons reach their submit handlers without click redraw',async()=>{
  for(const id of ['ollama-chat-form','skill-trial-form','experiment-form','agent-form','relationship-form']){
   const target=form(id,{}),before=renders;await click(button(target));assert.equal(renders,before);assert.equal(target.isConnected,true);
  }
 });
 await t.test('polling updates progress while an input has focus without detaching its form',async()=>{
  await click(button(null,{page:'llm'}));
  const focused=form('focused-settings',{model:'draft'}),before=renders;
  globalThis.document.activeElement={matches:()=>true};
  await click(button(null,{liveRefresh:''}));
  assert.equal(renders,before);assert.equal(focused.isConnected,true);
  assert.match(nodes.get('[data-execution-progress]').outerHTML,/aria-label="實驗進度"/);
  globalThis.document.activeElement=null;
 });
 await t.test('warmup button submits the saved model independently of an unsaved draft',async()=>{
  await click(button(null,{page:'llm'}));await click(button(null,{modelWarmup:''}));
  const warmups=calls.filter(c=>c.path==='/api/v1/llm/ollama/warmup');assert.equal(warmups.length,1);
  assert.equal(runtime.provider.warmup.config.model,'qwen3-coder:30b');assert.match(html,/等待模型暖機完成/);
  assert.equal(calls.filter(c=>c.path==='/api/v1/llm/skills/runs').length,1);
 });
 await t.test('Log navigation and search use the real app handlers while preserving focused filter inputs',async()=>{
  await click(button(null,{page:'logs'}));for(let i=0;i<20;i++)await Promise.resolve();assert.match(html,/模組 Log/);
  const search=form('debug-log-form',{module:'llm',level:'ERROR',q:'timeout & model',runId:'RUN-one'});
  globalThis.document.activeElement={matches:()=>true};const before=renders;
  await submit(search);for(let i=0;i<20;i++)await Promise.resolve();
  assert.equal(search.isConnected,true);assert.equal(renders,before);
  assert.match(nodes.get('[data-log-results]').outerHTML,/符合篩選/);
  const logCalls=calls.filter(c=>c.path.startsWith('/api/v1/debug/logs?'));
  const query=new URL('http://localhost'+logCalls.at(-1).path).searchParams;assert.equal(query.get('q'),'timeout & model');assert.equal(query.get('level'),'ERROR');
  globalThis.document.activeElement=null;
 });
 await t.test('Python repair navigation and Start post through the actual app listeners',async()=>{
  runtime.provider.busy=false;runtime.provider.warmup.status='PRELOAD_PASS';
  runtime.repair={engine:'nanobot-python-repair-v1',sdk:{available:true,version:'0.3.5'},latestRun:null,runs:[]};
  await click(button(null,{page:'repair'}));await click(button(null,{liveRefresh:''}));
  assert.match(html,/Python 修復實驗/);await click(button(null,{repairStart:''}));
  const starts=calls.filter(c=>c.path==='/api/v1/repair/runs');assert.equal(starts.length,1);
  const body=JSON.parse(starts[0].options.body);assert.equal(body.callBudget,8);assert.equal(body.providerRevision,saved.revision);assert.equal(body.registry.agents.length,5);
 });
});
