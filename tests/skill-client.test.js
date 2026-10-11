import test from 'node:test';
import assert from 'node:assert/strict';
import {RuntimeClient,validateRuntime,validateSkills} from '../dist/js/runtime-client.js';
import {skillView,skillMarkdown} from '../dist/js/skill-view.js';
import {initialRegistry} from '../dist/js/agents.js';
const stamp='2026-10-11T12:00:00Z',hash='a'.repeat(64);
const caps={schemaVersion:1,mode:'native-tools',serviceId:'test-service',csrfToken:'at-least-twenty-characters-test-token',skillEngine:'local-rule-search-v1'};
const skill=()=>({name:'normalize-support-title',description:'Normalize support titles.',body:'1. Return the input unchanged.\n',hash,policy:{unicode_nfkc:false,casefold:false,trim:false,collapse_whitespace:false}});
const metric=(passed,total)=>({passed,total,score:passed/total,loss:total-passed});
const version=()=>({id:'SKV-baseline',label:'S0',parentId:null,runId:null,createdAt:stamp,skill:skill(),evidence:null});
const workspace=()=>({schemaVersion:1,engine:'local-rule-search-v1',revision:1,activeVersionId:'SKV-baseline',active:version(),versions:[version()],actions:[],runs:[],latestRun:null});
const snapshot=()=>({schemaVersion:1,mode:'native-tools',serviceId:caps.serviceId,serverTime:stamp,latestRun:null,runs:[],skills:workspace()});
const run=()=>({id:'RUN-skill',requestId:'request',task:'skill-evolution',mode:'native-tools',status:'completed',createdAt:stamp,updatedAt:stamp,checksPassed:true,
  agents:initialRegistry().agents.map(a=>({...a,status:'completed',task:'measured work',pid:1234,processAlive:false,updatedAt:stamp,startedAt:stamp,endedAt:stamp,exitCode:0,logTail:'actual output'})),events:[],artifacts:['candidate-1.md','review.json'],
  skillConfig:{baseline:version(),maxCandidates:1,provenance:{datasetRevision:'title-normalizer-v1',datasetHash:hash,evaluatorHash:hash}},
  skillProgress:{engine:'local-rule-search-v1',phase:'reviewer',selectedId:'C1',candidates:[{id:'C0',skill:skill(),training:metric(3,20),validation:metric(2,10)},{id:'C1',mutation:'casefold',skill:{...skill(),hash:'b'.repeat(64),body:'1. Apply Unicode case folding.\n',policy:{...skill().policy,casefold:true}},training:metric(6,20),validation:metric(3,10)}],evaluations:{training:100,validation:20,heldout:40,verification:60},trainingFailures:[]},
  skillResult:{eligible:true,decision:'ready-for-human-review',selectedSkill:skill(),selectedValidation:metric(3,10),heldout:{baseline:metric(4,20),selected:metric(7,20)}}});
const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});
const view=(data=snapshot(),extra={})=>({data,capabilities:caps,error:null,lastSuccess:stamp,pollCount:3,interval:2000,enabled:true,skillLimit:4,actionBusy:false,...extra});

test('skill workspace validation rejects broken active pointers, duplicate versions and fabricated metric formats',()=>{
  assert.equal(validateSkills(workspace()).revision,1);
  for(const mutate of [s=>s.activeVersionId='SKV-missing',s=>s.versions.push(version()),s=>s.active.skill.hash='bad',s=>s.revision=true]){
    const data=snapshot();mutate(data.skills);assert.throws(()=>validateRuntime(data));
  }
  const data=snapshot();data.skills.latestRun=run();assert.doesNotThrow(()=>validateRuntime(data));
  data.skills.latestRun.skillProgress.candidates[1].validation.score=9;assert.throws(()=>validateRuntime(data));
});
test('skill controls gate approval on complete fresh evidence, unchanged baseline and no existing release',()=>{
  const data=snapshot();data.skills.latestRun=run();
  const approval=html=>html.match(/<button[^>]*data-skill-approve[^>]*>/)[0];
  assert.equal(approval(skillView(view(data))).includes('disabled'),false);
  for(const state of [view(data,{error:'offline'}),view(data,{actionBusy:true})])assert.ok(approval(skillView(state)).includes('disabled'));
  data.skills.latestRun.status='cancelled';assert.ok(approval(skillView(view(data))).includes('disabled'));
  data.skills.latestRun.status='completed';data.skills.latestRun.skillResult.eligible=false;assert.match(skillView(view(data)),/沒有符合發布條件/);
  data.skills.latestRun.skillResult.eligible=true;data.skills.activeVersionId='SKV-new';assert.ok(approval(skillView(view(data))).includes('disabled'));
  data.skills.activeVersionId='SKV-baseline';data.skills.versions.push({...version(),id:'SKV-new',runId:'RUN-skill'});assert.match(skillView(view(data)),/已建立版本/);
});
test('measured view renders real count denominators, rule changes, hashes and escaped trace text',()=>{
  const data=snapshot();data.skills.latestRun=run();
  const payload='<img src=x onerror="alert(1)">';
  data.skills.latestRun.skillProgress.trainingFailures=[{taskId:'TR-01',input:payload,output:payload,expected:'clean'}];
  data.skills.latestRun.skillConfig.baseline.skill.body=payload;
  const html=skillView(view(data));assert.equal(html.includes(payload),false);assert.match(html,/&lt;img/);
  assert.match(html,/3 \/ 10/);assert.match(html,/160/);assert.match(html,/casefold/);assert.match(html,/local-rule-search-v1/);
  assert.match(html,/candidate-1\.md/);assert.match(html,/<svg/);
  assert.match(skillMarkdown(version()),/name: normalize-support-title/);
});
test('skill requests use local tokens and current revisions; selecting history does not submit work',async()=>{
  const calls=[];let data=snapshot();data.skills.latestRun=run();
  const client=new RuntimeClient({fetcher:async(path,options)=>{
    calls.push({path,options});
    if(path.endsWith('capabilities'))return response(caps);
    if(path==='/api/v1/runtime')return response(data);
    return response(path==='/api/v1/runtime/runs/RUN-skill'?run():{});
  }});
  await client.refresh();client.skillLimit=2;await client.startSkill(initialRegistry());
  await client.approveSkill('RUN-skill');await client.activateSkill('SKV-baseline');await client.selectSkillRun('RUN-skill');
  assert.equal(client.snapshot().selectedSkillRun.id,'RUN-skill');
  await client.selectSkillRun('');assert.equal(client.selectedSkillRun,null);
  const posts=calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,3);
  assert.ok(posts.every(c=>c.options.headers['X-Lab-Token']===caps.csrfToken));
  assert.equal(JSON.parse(posts[0].options.body).maxCandidates,2);
  assert.ok(posts.every(c=>JSON.parse(c.options.body).expectedRevision===1));
});
test('uncertain submit retries retain immutable body/id while definitive rejection allows a corrected submission',async()=>{
  let fail='network';const submitted=[];
  const client=new RuntimeClient({fetcher:async(path,options)=>{
    if(path.endsWith('capabilities'))return response(caps);
    if(options.method==='POST'){
      submitted.push(JSON.parse(options.body));
      if(fail==='network')throw Error('lost response');
      if(fail==='validation')return {ok:false,status:400,json:async()=>({error:'invalid role'})};
      return response({});
    }
    return response(snapshot());
  }});
  await client.refresh();const registry=initialRegistry();await assert.rejects(client.startSkill(registry));
  registry.agents[0].name='Changed after failed request';client.skillLimit=1;
  fail=null;await client.startSkill(registry);assert.deepEqual(submitted[0],submitted[1]);
  fail='validation';await assert.rejects(client.startSkill(registry));assert.equal(client.pendingSkillSubmission,null);
  fail=null;await client.startSkill(registry);assert.notEqual(submitted[2].requestId,submitted[3].requestId);
  assert.equal(submitted[3].maxCandidates,1);assert.equal(client.actionBusy,false);
});
test('a stale service cannot submit skill work or silently substitute demo scores',async()=>{
  let posts=0;
  const client=new RuntimeClient({fetcher:async(path,options)=>{if(options.method==='POST')posts++;throw Error('offline');}});
  await assert.rejects(client.startSkill(initialRegistry()),/尚未連線/);
  assert.equal(posts,0);assert.equal(client.actionBusy,false);assert.equal(client.data,null);
  const html=skillView(client.snapshot());assert.match(html,/服務未連線/);assert.match(html,/尚未評估/);
});
test('skill trial is pinned to the current server revision and preserves input across updates',async()=>{
  const calls=[];
  const client=new RuntimeClient({fetcher:async(path,options)=>{
    if(path.endsWith('capabilities'))return response(caps);
    if(path==='/api/v1/skills/execute'){
      calls.push(JSON.parse(options.body));
      return response({versionId:'SKV-baseline',label:'S0',skillHash:hash,input:calls[0].text,output:calls[0].text});
    }
    return response(snapshot());
  }});
  await client.refresh();await client.trySkill('  TEXT  ');
  assert.deepEqual(calls,[{text:'  TEXT  ',expectedRevision:1}]);
  assert.equal(client.snapshot().trialInput,'  TEXT  ');assert.equal(client.skillTrial.output,'  TEXT  ');
  client.data.skills.activeVersionId='SKV-other';
  assert.match(skillView(client.snapshot()),/先前啟用版本/);
});
