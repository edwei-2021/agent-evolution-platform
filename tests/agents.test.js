import test from 'node:test';
import assert from 'node:assert/strict';
import {initialRegistry,validateRegistry,registryStats,filterAgents,saveAgent,removeAgent,addRelationship} from '../dist/js/agents.js';
import {initialState,validateState,release} from '../dist/js/domain.js';
import {DemoAdapter} from '../dist/js/adapter.js';
import {agentsView,agentForm,relationshipForm} from '../dist/js/agent-view.js';
const storage=()=>{let saved=null;return {getItem(){return saved;},setItem(_,value){saved=value;}};};

test('seed roles and skill assignments have valid directed relationships and no live agents',()=>{
  const r=initialRegistry();
  assert.equal(validateRegistry(r),r);
  assert.deepEqual(registryStats(r),{total:5,enabled:5,connected:0,skills:5,relationships:6});
  assert.equal(new Set(r.agents.map(a=>a.role)).size,5);
});
test('legacy workspace migration preserves experiments and releases without mutating backup',()=>{
  const s=initialState(),released=release(s,s.experiments[0],'2026-10-11T12:00:00Z','REL-legacy');
  const old={...released,schemaVersion:1};delete old.registry;
  const before=structuredClone(old),next=validateState(old);
  assert.deepEqual(old,before);
  assert.equal(next.schemaVersion,2);
  assert.deepEqual(next.experiments,old.experiments);
  assert.deepEqual(next.releases,old.releases);
  assert.equal(next.activeReleaseId,'REL-legacy');
  assert.equal(next.registry.agents.length,5);
  const db={getItem(){return JSON.stringify(old);},setItem(){}};
  assert.equal(new DemoAdapter(db).recoveryWarning,false);
});
test('agent edits, disabling and new assignments persist through reload and JSON export',()=>{
  const db=storage(),api=new DemoAdapter(db),a=api.snapshot().registry.agents[1];
  a.enabled=false;a.model='example-model';a.skillIds.push('evaluate-python');
  api.saveAgent(a);
  a.name='outside mutation';
  const b=new DemoAdapter(db);
  assert.equal(b.snapshot().registry.agents[1].enabled,false);
  assert.equal(b.snapshot().registry.agents[1].name,'nanobot Worker');
  assert.deepEqual(validateState(JSON.parse(JSON.stringify(b.snapshot()))),b.snapshot());
  assert.equal(registryStats(b.snapshot().registry).skills,5);
});
test('removing an agent cascades only its relationships and leaves experiment records intact',()=>{
  const api=new DemoAdapter(storage()),before=api.snapshot();
  api.removeAgent('AG-004');
  const after=api.snapshot();
  assert.equal(after.registry.agents.length,4);
  assert.ok(after.registry.relationships.every(r=>r.from!=='AG-004'&&r.to!=='AG-004'));
  assert.deepEqual(after.experiments,before.experiments);
  assert.equal(before.registry.agents.length,5);
});
test('relation validation rejects absent endpoints, duplicates and self links but permits feedback loops',()=>{
  const r=initialRegistry(),link={id:'LINK-new',from:'AG-002',to:'AG-003',type:'task',artifact:'training task'};
  const next=addRelationship(r,link);
  assert.equal(next.relationships.length,7);
  assert.throws(()=>addRelationship(next,{...link,id:'LINK-duplicate'}));
  assert.throws(()=>addRelationship(r,{...link,to:'missing'}));
  assert.throws(()=>addRelationship(r,{...link,to:link.from}));
  assert.equal(r.relationships.length,6);
});
test('invalid imported registry is rejected atomically instead of replacing the workspace',()=>{
  const api=new DemoAdapter(storage()),before=api.snapshot(),bad=structuredClone(before);
  bad.registry.agents[0].connection='connected';
  assert.throws(()=>api.import(bad));
  assert.deepEqual(api.snapshot(),before);
  for(const change of [a=>a.maxSteps=0,a=>a.temperature=3,a=>a.skillIds=['unknown'],a=>a.tools=['same','same'],a=>a.id='<unsafe>',a=>a.role='__proto__']){
    const r=initialRegistry();change(r.agents[0]);assert.throws(()=>validateRegistry(r));
  }
  const r=initialRegistry();r.agents.push(structuredClone(r.agents[0]));assert.throws(()=>validateRegistry(r));
});
test('search and role filtering match Skill IDs, tools and Runtime without changing totals',()=>{
  const r=initialRegistry();
  assert.equal(filterAgents(r,{query:'PYTHON-FIX'}).length,1);
  assert.equal(filterAgents(r,{query:'Python 修復與驗證'}).length,1);
  assert.equal(filterAgents(r,{query:'run-trusted-tests',role:'evaluator'}).length,1);
  assert.equal(filterAgents(r,{query:'nanobot',role:'reviewer'}).length,0);
  assert.equal(registryStats(r).total,5);
});
test('empty registry is valid and renders actionable empty states',()=>{
  const s=initialState();s.registry={agents:[],relationships:[]};
  validateState(s);
  assert.match(agentsView(s),/新增代理人/);
  assert.match(agentsView(s),/尚無工作關係/);
  assert.deepEqual(registryStats(s.registry),{total:0,enabled:0,connected:0,skills:0,relationships:0});
});
test('agent, model, tool and relation values are escaped in views and edit forms',()=>{
  const s=initialState(),payload='<img src=x onerror="alert(1)">';
  s.registry.agents[0].name=payload;s.registry.agents[0].model=payload;s.registry.agents[0].tools=[payload];
  s.registry.relationships[0].artifact=payload;
  validateState(s);
  for(const html of [agentsView(s,{selectedId:'AG-001'}),agentForm(s.registry.agents[0]),relationshipForm(s.registry)]){
    assert.equal(html.includes(payload),false);
    assert.match(html,/&lt;img/);
  }
});
test('Worker Skill detail follows active demo release and rollback',()=>{
  const s=initialState(),before=agentsView(s,{selectedId:'AG-002'});
  assert.match(before,/S0 · baseline/);
  const published=release(s,s.experiments[0],'2026-10-11T12:00:00Z','REL-skill');
  assert.match(agentsView(published,{selectedId:'AG-002'}),/候選展示版本/);
  assert.match(agentsView(published,{selectedId:'AG-002'}),/Reproduce the failure/);
  published.activeReleaseId='baseline';
  assert.match(agentsView(published,{selectedId:'AG-002'}),/S0 · baseline/);
});
test('registry bounds protect imports and invalid saves do not modify the previous state',()=>{
  const r=initialRegistry(),a=structuredClone(r.agents[0]);a.id='AG-new';a.name='extra';
  const next=saveAgent(r,a);assert.equal(next.agents.length,6);assert.equal(r.agents.length,5);
  const oversized={agents:Array.from({length:31},(_,i)=>({...a,id:`AG-${i}`})),relationships:[]};
  assert.throws(()=>validateRegistry(oversized));
  assert.throws(()=>validateRegistry({...r,relationships:Array(121).fill(r.relationships[0])}));
  assert.throws(()=>removeAgent(r,'unknown'));
});
