import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

// Run the real app event listeners without a browser dependency. Model the
// connected-form rule: replacing #main detaches its form before default submit.
test('app form events preserve settings through click, submit, navigation and LLM start',async t=>{
 const names=['document','window','location','history','FormData','fetch','setTimeout','clearTimeout','setInterval','clearInterval'];
 const originals=new Map(names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
 t.after(()=>{for(const [name,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];}});
 const listeners=new Map(),windowListeners=new Map(),forms=new Set(),calls=[];let openChanges=false,delayHistory=false,historyReply;
 const node=()=>({textContent:'',dataset:{},classList:{add(){},remove(){},toggle(){}},setAttribute(){},addEventListener(){}});
 const main=node();let html='',renders=0;
 Object.defineProperty(main,'innerHTML',{get:()=>html,set:value=>{html=value;renders++;for(const form of forms)form.isConnected=false;}});
 const nodes=new Map([['#main',main]]);
 const add=(map,type,handler)=>map.set(type,[...(map.get(type)||[]),handler]);
 const dispatch=async(type,event)=>{for(const handler of listeners.get(type)||[])await handler(event);};
 globalThis.document={activeElement:null,addEventListener:(type,handler)=>add(listeners,type,handler),querySelector:selector=>{
  if(selector==='dialog[open]')return null;
  if(selector==='.change-history details[open]')return openChanges?{}:null;
  if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);
 },querySelectorAll:()=>[],createElement:()=>({innerHTML:'',querySelector(){return {outerHTML:this.innerHTML};}})};
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
 let challengeData={schemaVersion:1,version:'python-challenges-v1',revision:1,questions:JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v1.json',import.meta.url)))};
 globalThis.fetch=async(path,options)=>{
  calls.push({path,options});let value,ok=true;
  if(path.endsWith('/capabilities'))value={schemaVersion:1,mode:'native-tools',serviceId:runtime.serviceId,csrfToken:'a-valid-local-session-token'};
  else if(path==='/api/v1/runtime')value=runtime;
  else if(path==='/api/v1/llm/ollama')value=saved;
  else if(path==='/api/v1/challenges'){
   if(options.method==='POST'){const body=JSON.parse(options.body);assert.equal(body.expectedRevision,challengeData.revision);challengeData={...challengeData,revision:challengeData.revision+1,questions:[...challengeData.questions,{...body.challenge,id:'CH-created-fixture'}]};}
   value=challengeData;
  }
  else if(path==='/api/v1/challenges/presets/repair-v3'){
   const body=JSON.parse(options.body);assert.equal(body.expectedRevision,challengeData.revision);
   const seeds=JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v3.json',import.meta.url)));
   const selected=new Set();for(const level of ['easy','medium','hard'])for(const [split,n] of [['train',2],['validation',1],['heldout',1]]){
    for(const q of seeds.filter(q=>q.difficulty===level&&q.split===split).slice(body.batch*n,(body.batch+1)*n))selected.add(q.id);
   }
   const ids=new Set(challengeData.questions.map(q=>q.id));
   challengeData={...challengeData,version:'python-challenges-v3',revision:challengeData.revision+1,
    questions:[...challengeData.questions,...seeds.filter(q=>!ids.has(q.id))].map(q=>({...q,enabled:selected.has(q.id)}))};
   runtime.challenges={version:challengeData.version,revision:challengeData.revision,ready:true,counts:{train:6,validation:3,heldout:3}};value=challengeData;
  }
  else if(path==='/api/v1/challenges/presets/repair-v2'){
   const body=JSON.parse(options.body);assert.deepEqual(body,{expectedRevision:challengeData.revision});
   const seeds=JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v2.json',import.meta.url)));
   challengeData={...challengeData,version:'python-challenges-v2',revision:challengeData.revision+1,questions:[...challengeData.questions.map(q=>({...q,enabled:false})),...seeds]};
   runtime.challenges={version:challengeData.version,revision:challengeData.revision,ready:true,counts:{train:6,validation:3,heldout:3}};value=challengeData;
  }
  else if(path.startsWith('/api/v1/challenges/')){
   const body=JSON.parse(options.body),id=path.split('/')[4];assert.equal(body.expectedRevision,challengeData.revision);
   challengeData={...challengeData,revision:challengeData.revision+1,questions:path.endsWith('/delete')?challengeData.questions.filter(q=>q.id!==id):challengeData.questions.map(q=>q.id===id?{...body.challenge,id}:q)};value=challengeData;
  }
  else if(path.startsWith('/api/v1/debug/skills?'))value={schemaVersion:1,historyOnly:true,offset:Number(new URL(path,'http://localhost').searchParams.get('offset')),limit:20,total:0,runs:[]};
  else if(path.startsWith('/api/v1/debug/skills/'))value={schemaVersion:1,historyOnly:true,runId:path.split('/').at(-1),task:'gepa-evolution',runStatus:'completed',baseline:{text:'Saved Skill'},conditions:{model:'fixture'},records:[],warnings:[],approvedVersions:[],searchAudit:null};
  else if(path.startsWith('/api/v1/debug/changes/')){
   const url=new URL(path,'http://localhost'),id=url.pathname.split('/').at(-1),offset=Number(url.searchParams.get('offset')||0);
   value={schemaVersion:1,runId:id,runStatus:'completed',task:'gepa-evolution',verified:true,historyOnly:true,rollouts:[],totalRollouts:0,offset,limit:20,selectedRollout:url.searchParams.get('rollout')||'',trace:null,warnings:[],skillHistory:[{id:'baseline',kind:'baseline',before:'Recorded Skill',after:'Recorded Skill',changed:false,note:'Frozen baseline Skill'}]};
  }
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
  if(delayHistory&&path.startsWith('/api/v1/debug/changes/')){delayHistory=false;await new Promise(resolve=>{historyReply=resolve;});}
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
 await t.test('step trace navigation and refresh use read-only app handlers',async()=>{
  runtime.runs=[{id:'RUN-steps',status:'completed',createdAt:'2026-10-12T08:00:00Z'}];
  await click(button(null,{page:'steps'}));assert.match(html,/逐步執行紀錄/);await click(button(null,{stepRefresh:''}));
  assert.equal(calls.filter(c=>c.path==='/api/v1/gepa/runs').length,0);
 });
 await t.test('GEPA navigation, profile and Start use real app handlers with pinned revisions',async()=>{
  const skill={name:'python-fix-and-verify',description:'Bounded repair',body:'Read, repair, test.',hash:'a'.repeat(64)};
  runtime.gepa={schemaVersion:1,engine:'gepa-nanobot-repair-v1',revision:1,activeVersionId:'GSV-baseline',active:{id:'GSV-baseline',skill},versions:[{id:'GSV-baseline',label:'G0',skill,runId:null}],sdk:{available:true,version:'0.3.5'},optimizer:{available:true,version:'0.1.4'},latestRun:null,runs:[]};
  runtime.provider.busy=false;
  await click(button(null,{page:'gepa'}));await click(button(null,{liveRefresh:''}));assert.match(html,/GEPA 技能最佳化/);
  await click(button(null,{gepaStart:''}));const starts=calls.filter(c=>c.path==='/api/v1/gepa/runs');assert.equal(starts.length,1);
  const body=JSON.parse(starts[0].options.body);assert.equal(body.profile,'smoke');assert.equal(body.taskCallBudget,8);assert.equal(body.metricBudget,10);assert.equal(body.searchMode,'explore');assert.equal(body.providerRevision,saved.revision);assert.equal(body.expectedRevision,1);
 });
 await t.test('GEPA completion refreshes the actual result while focused settings remain connected',async()=>{
  const baseline=runtime.gepa.active.skill,stamp='2026-01-01T00:00:00Z';
  runtime.gepa.latestRun={id:'RUN-focused-result',task:'gepa-evolution',mode:'native-tools',status:'running',createdAt:stamp,updatedAt:stamp,events:[],artifacts:[],agents:['coordinator','worker','evaluator','reflector','reviewer'].map(id=>({id,name:id,status:'completed',updatedAt:stamp,pid:null,processAlive:false,logTail:''})),
   gepaConfig:{engine:'gepa-nanobot-repair-v1',sdk:{version:'0.3.5'},optimizer:{version:'0.1.4'},baseline:{id:'GSV-baseline',skill:baseline},profile:'smoke',callBudget:162,metricBudget:8,proposalBudget:2,counts:{train:4,validation:2,heldout:4},provider:{config:{model:'fixture-model'}}}};
  await click(button(null,{page:'gepa'}));await click(button(null,{liveRefresh:''}));assert.match(html,/待完成評估與審查/);
  const focused=form('focused-gepa-settings',{taskCalls:'9'}),before=renders,posts=calls.filter(c=>c.options?.method==='POST').length;
  globalThis.document.activeElement={matches:()=>true};
  runtime.gepa.latestRun.status='completed';
  runtime.gepa.latestRun.gepaResult={engine:'gepa-nanobot-repair-v1',checksPassed:true,eligible:false,baselineSkill:baseline,selectedSkill:baseline,evidenceHash:'c'.repeat(64),proposals:0,validationScores:[1],calls:40,rollouts:17,metricEvaluations:5,
   final:{baseline:{validation:{passed:2,total:2},heldout:{passed:4,total:4}},selected:{validation:{passed:2,total:2},heldout:{passed:4,total:4}}}};
  await click(button(null,{liveRefresh:''}));
  assert.equal(renders,before);assert.equal(focused.isConnected,true);
  assert.match(nodes.get('[data-gepa-results]').outerHTML,/未產生候選・尚未完成有效比較/);
  assert.match(nodes.get('[data-gepa-results]').outerHTML,/0 題 · 0 個百分點/);
  assert.equal(calls.filter(c=>c.options?.method==='POST').length,posts);
  globalThis.document.activeElement=null;
 });
 await t.test('GEPA page loads saved task records automatically and idle polls add no history reads',async()=>{
  for(let i=0;i<20;i++)await Promise.resolve();
  const reads=()=>calls.filter(c=>c.path.startsWith('/api/v1/debug/changes/')).length;
  const before=reads();assert.ok(before>0);
  assert.ok(calls.some(c=>c.path.startsWith('/api/v1/debug/changes/RUN-focused-result')));
  await click(button(null,{liveRefresh:''}));for(let i=0;i<20;i++)await Promise.resolve();
  assert.equal(reads(),before);
  assert.match(html,/逐題修復與 Skill 對照紀錄/);
  assert.ok(calls.filter(c=>c.path.startsWith('/api/v1/debug/changes/')).every(c=>c.options.method==='GET'));
 });
 await t.test('profile selection and explicit time changes reach actual submission with final workload shown',async()=>{
  const target=(selector,value)=>({value,dataset:{},matches:s=>s===selector,hasAttribute:()=>false});
  await dispatch('change',{target:target('[data-gepa-profile]','full')});
  assert.match(html,/data-gepa-metrics[^>]*value="26"/);assert.match(html,/data-gepa-seconds[^>]*value="7200"/);
  assert.match(html,/最後評測 60 次 = 86 次 rollout/);
  await dispatch('change',{target:target('[data-gepa-seconds]','3600')});
  await click(button(null,{gepaStart:''}));const posts=calls.filter(c=>c.path==='/api/v1/gepa/runs');
  const body=JSON.parse(posts.at(-1).options.body);
  assert.equal(body.profile,'full');assert.equal(body.metricBudget,26);assert.equal(body.proposalBudget,1);assert.equal(body.maxSeconds,3600);
 });
 await t.test('actual history button reads only GET and open source details survive status polling',async()=>{
  const posts=calls.filter(c=>c.options?.method==='POST').length;
  await click(button(null,{changeLoad:'RUN-focused-result'}));assert.match(html,/Recorded Skill/);
  assert.equal(calls.filter(c=>c.options?.method==='POST').length,posts);
  const panel=nodes.get('[data-change-panel]')||node();nodes.set('[data-change-panel]',panel);
  panel.dataset.changeRevision=html.match(/data-change-revision="(\d+)"/)[1];panel.outerHTML='preserved open details';
  openChanges=true;const before=renders;await click(button(null,{liveRefresh:''}));
  assert.equal(renders,before);assert.equal(panel.outerHTML,'preserved open details');openChanges=false;
 });
 await t.test('background history completion preserves details opened while the GET is in flight',async()=>{
  const oldRun=runtime.gepa.latestRun;
  runtime.gepa.latestRun={...oldRun,id:'RUN-background-records'};
  delayHistory=true;await click(button(null,{liveRefresh:''}));
  assert.equal(typeof historyReply,'function');
  const panel=nodes.get('[data-change-panel]');panel.dataset.changeRunId='RUN-background-records';
  panel.outerHTML='open source preserved during background read';openChanges=true;
  historyReply();for(let i=0;i<30;i++)await Promise.resolve();
  assert.equal(panel.outerHTML,'open source preserved during background read');
  openChanges=false;runtime.gepa.latestRun=oldRun;await click(button(null,{liveRefresh:''}));
  for(let i=0;i<30;i++)await Promise.resolve();
 });
 await t.test('Python repair navigation and Start post through the actual app listeners',async()=>{
  runtime.provider.busy=false;runtime.provider.warmup.status='PRELOAD_PASS';
  runtime.repair={engine:'nanobot-python-repair-v1',sdk:{available:true,version:'0.3.5'},latestRun:null,runs:[]};
  await click(button(null,{page:'repair'}));await click(button(null,{liveRefresh:''}));
  assert.match(html,/Python 修復實驗/);await click(button(null,{repairStart:''}));
  assert.match(html,/固定單題：整數範圍 clamp/);assert.match(html,/開始單題 Python 修復/);
  const starts=calls.filter(c=>c.path==='/api/v1/repair/runs');assert.equal(starts.length,1);
  const body=JSON.parse(starts[0].options.body);assert.equal(body.callBudget,8);assert.equal(body.providerRevision,saved.revision);assert.equal(body.registry.agents.length,5);
 });
 await t.test('Strata selection, typed URL and effort reach the real save handler without model requests',async()=>{
  failure=false;runtime.provider.busy=false;
  await click(button(null,{page:'integrations'}));for(let i=0;i<20;i++)await Promise.resolve();
  const before=calls.length;
  await dispatch('change',{target:{value:'strata',matches:selector=>selector==='[data-model-provider]'}});
  assert.match(html,/name="baseUrl"/);assert.equal(calls.length,before);
  const fields={provider:'strata',baseUrl:'http://fixture.invalid:8081/v1',apiKeyEnv:'FIXTURE_KEY',reasoningEffort:'none',model:'fixture-strata',metadataTimeout:'10',inferenceTimeout:'600',maxTokens:'256'};
  await submit(form('ollama-settings-form',fields));assert.equal(saved.config.provider,'strata');assert.equal(saved.config.baseUrl,fields.baseUrl);assert.equal(saved.config.apiKeyEnv,'FIXTURE_KEY');assert.equal(saved.config.reasoningEffort,'none');assert.equal(saved.config.maxTokens,256);
  assert.ok(!calls.slice(before).some(c=>c.path.endsWith('/metadata')||c.path.endsWith('/chat')));
 });
 await t.test('challenge navigation, editing, saving, creation and deletion use actual app handlers',async()=>{
  await click(button(null,{page:'challenges'}));for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(html,/多難度 Python 題庫/);assert.match(html,/空白正規化/);
  await click(button(null,{bankSelect:challengeData.questions[0].id}));assert.match(html,/id="challenge-form"/);
  const q=challengeData.questions[0],fields={...q,title:'Edited through real form',visible:JSON.stringify(q.visible),hidden:JSON.stringify(q.hidden),sources:q.sources.join('\n')};delete fields.id;delete fields.enabled;
  const edited=form('challenge-form',fields),before=renders;await click(button(edited));assert.equal(renders,before);await submit(edited);
  assert.equal(challengeData.questions[0].title,'Edited through real form');assert.equal(challengeData.questions[0].enabled,false);
  await click(button(null,{bankNew:''}));assert.match(html,/新增題目/);
  await submit(form('challenge-form',{...fields,group:'new-fixture-family',enabled:'on'}));assert.equal(challengeData.questions.at(-1).id,'CH-created-fixture');
  globalThis.window.confirm=()=>true;await click(button(null,{bankDelete:'CH-created-fixture'}));assert.ok(!challengeData.questions.some(q=>q.id==='CH-created-fixture'));
  assert.equal(calls.filter(c=>c.path==='/api/v1/gepa/runs').length,2,'editing questions must not start GEPA');
 });

 await t.test('repair and bank entrypoints prepare the bank without dispatch; explicit Start submits the bank revision',async()=>{
  const counts=Object.fromEntries(['train','validation','heldout'].map(s=>[s,challengeData.questions.filter(q=>q.enabled&&q.split===s).length]));
  runtime.challenges={revision:challengeData.revision,version:challengeData.version,ready:true,counts};
  runtime.provider={revision:saved.revision,config:{...saved.config,maxTokens:256},busy:false};
  const before=calls.filter(c=>c.options?.method==='POST').length;
  for(const origin of ['repair','challenges']){
   await click(button(null,{page:origin}));for(let i=0;i<20;i++)await Promise.resolve();
   assert.match(html,/data-bank-gepa/);
   await click(button(null,{bankGepa:''}));
   assert.match(html,/<option value="bank" selected>/);assert.match(html,/下一輪使用：多難度題庫/);
   assert.match(html,/data-gepa-start[^>]*disabled/);assert.match(html,/開始題庫演化/);
   assert.equal(runtime.provider.config.maxTokens,256,'preparation must preserve the saved output cap');
  }
  assert.equal(calls.filter(c=>c.options?.method==='POST').length,before,'preparation must not dispatch any workflow');
  assert.match(html,/目前已儲存的最大輸出 tokens：256/);
  assert.match(html,/data-page="integrations"/);
  await click(button(null,{page:'integrations'}));for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(html,/name="maxTokens"/);
  await submit(form('ollama-settings-form',{...saved.config,maxTokens:'1024'}));
  assert.equal(saved.config.maxTokens,1024);
  // The server's next read reflects the settings mutation, as in production.
  runtime.provider={revision:saved.revision,config:{...saved.config},busy:false};
  await click(button(null,{page:'gepa'}));await click(button(null,{liveRefresh:''}));
  assert.ok(!html.match(/data-gepa-start[^>]*disabled/),html.match(/error-banner[\s\S]*?<\/div>/)?.[0]||'Bank start remained disabled');
  await click(button(null,{gepaStart:''}));
  const posts=calls.filter(c=>c.path==='/api/v1/gepa/runs');assert.equal(posts.length,3);
  const submitted=JSON.parse(posts.at(-1).options.body);
  assert.equal(submitted.profile,'bank');assert.equal(submitted.bankRevision,challengeData.revision);
  assert.equal(submitted.metricBudget,45);assert.equal(submitted.proposalBudget,6);assert.equal(submitted.taskCallBudget,10);assert.equal(submitted.maxSeconds,7200);assert.equal(submitted.searchMode,'explore');
  const target=(selector,value)=>({value,dataset:{},matches:s=>s===selector,hasAttribute:()=>false});
  const postsBefore=calls.filter(c=>c.options?.method==='POST').length;
  await dispatch('change',{target:target('[data-gepa-mode]','standard')});
  assert.match(html,/data-gepa-metrics[^>]*value="10"/);assert.match(html,/data-gepa-proposals[^>]*value="1"/);
  await dispatch('change',{target:target('[data-gepa-mode]','explore')});
  assert.match(html,/data-gepa-metrics[^>]*value="45"/);assert.match(html,/data-gepa-proposals[^>]*value="6"/);
  assert.equal(calls.filter(c=>c.options?.method==='POST').length,postsBefore);

  assert.equal(calls.filter(c=>c.path==='/api/v1/repair/runs').length,1,'bank Start must not repeat the single repair');
 });

 await t.test('actual V2 install button switches future bank with one explicit POST and no model dispatch',async()=>{
  await click(button(null,{page:'challenges'}));for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(html,/data-bank-v2/);
  const before=calls.length;await click(button(null,{bankV2:''}));
  const posted=calls.slice(before).filter(c=>c.options?.method==='POST');
  assert.equal(posted.length,1);assert.equal(posted[0].path,'/api/v1/challenges/presets/repair-v2');
  assert.equal(challengeData.version,'python-challenges-v2');assert.equal(challengeData.questions.filter(q=>q.enabled).length,12);
  assert.match(html,/data-bank-v2 disabled/);
  await click(button(null,{bankGepa:''}));assert.match(html,/data-gepa-metrics[^>]*value="45"/);
  assert.match(html,/data-gepa-proposals[^>]*value="6"/);
  assert.equal(calls.slice(before).filter(c=>c.options?.method==='POST').length,1);
 });

 await t.test('actual sixty-question catalog button freezes selected batch without starting a model',async()=>{
  await click(button(null,{page:'challenges'}));for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(html,/data-bank-v3/);const before=calls.length;
  await dispatch('change',{target:{value:'4',matches:s=>s==='[data-bank-v3-batch]'}});
  assert.equal(calls.length,before);await click(button(null,{bankV3:''}));
  const posts=calls.slice(before).filter(c=>c.options?.method==='POST');assert.equal(posts.length,1);
  assert.equal(posts[0].path,'/api/v1/challenges/presets/repair-v3');assert.equal(JSON.parse(posts[0].options.body).batch,4);
  assert.equal(challengeData.version,'python-challenges-v3');assert.equal(challengeData.questions.length,72);
  assert.equal(challengeData.questions.filter(q=>q.enabled).length,12);
  assert.equal(challengeData.questions.find(q=>q.id==='CH-normalize-whitespace').title,'Edited through real form');
 });

 await t.test('Skill archive navigation and exact Run queries read local records without mutations',async()=>{
  const posts=calls.filter(c=>c.options?.method==='POST').length;
  await click(button(null,{page:'skill-history'}));for(let i=0;i<30;i++)await Promise.resolve();
  assert.match(html,/Skill 產生紀錄/);
  await submit(form('skill-archive-form',{runId:'RUN-archived-fixture',task:'gepa-evolution'}));
  assert.ok(calls.some(c=>c.path==='/api/v1/debug/skills/RUN-archived-fixture'));
  assert.match(nodes.get('[data-skill-archive-results]').outerHTML,/Saved Skill/);
  await click(button(null,{skillArchiveRun:'RUN-other-archived'}));
  assert.ok(calls.some(c=>c.path==='/api/v1/debug/skills/RUN-other-archived'));
  assert.equal(calls.filter(c=>c.options?.method==='POST').length,posts);
 });

});
