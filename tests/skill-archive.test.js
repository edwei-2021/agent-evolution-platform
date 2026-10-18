import test from 'node:test';
import assert from 'node:assert/strict';
import {SkillArchiveClient,validateSkillArchive,skillArchiveView} from '../dist/js/skill-archive.js';
const fixture=(runId='RUN-one')=>({schemaVersion:1,runId,task:'gepa-evolution',runStatus:'completed',historyOnly:true,baselineVersionId:'GSV-baseline',baseline:{text:'Read and test.',hash:'a'.repeat(64)},conditions:{model:'fixture'},warnings:[],approvedVersions:[],searchAudit:{stop:{reasons:['iteration-reservation']}},records:[{id:'P001',status:'generated',origin:'recorded',startedAt:'2026-01-01',finishedAt:'2026-01-01',instruction:{text:'Inspect <boundary>.',hash:'b'.repeat(64)},parent:{text:'Read and test.',hash:'a'.repeat(64)},patch:'-Read and test.\n+Inspect <boundary>.',changed:true,matchesSelection:false,validationScore:0,trainingRefs:[{rolloutId:'R0004',score:0}],conditions:{model:'fixture',seed:0,metricEvaluations:5},errorType:null}]});
test('query view keeps generated unselected instructions, conditions, parent diff and real zero score',()=>{
 const d=validateSkillArchive(fixture()),html=skillArchiveView({data:d,index:{total:1,runs:[{id:d.runId,task:d.task,status:'completed'}]},offset:0,task:'',busy:false});
 for(const s of ['產生條件','Parent Skill','版本差異','未選用','搜尋驗證分數：0','metricEvaluations','R0004','下載此 Run 診斷包','核准版本 0 個'])assert.ok(html.includes(s),s);
 assert.match(html,/Inspect &lt;boundary&gt;/);assert.doesNotMatch(html,/Inspect <boundary>/);
 d.records[0].status='failed';d.records[0].errorType='ValueError';assert.match(skillArchiveView({data:d,offset:0}),/ValueError/);
});
test('malformed and oversized archive replies fail before display',()=>{
 for(const mutate of [d=>d.runId='../outside',d=>d.records[0].id='../../file',d=>d.records[0].instruction.text='a'.repeat(16001),d=>d.records[0].status='auto-approved',d=>d.records.push(...Array(32).fill(d.records[0]))]){const d=fixture();mutate(d);assert.throws(()=>validateSkillArchive(d));}
});
test('sixteen changed records cannot be presented as sixteen distinct Skill bodies',()=>{
 const d=fixture(),row=d.records[0];
 d.records=Array.from({length:16},(_,i)=>({...structuredClone(row),id:`P${String(i+1).padStart(3,'0')}`,novelty:i?'duplicate':'new',duplicateOf:i?'P001':null}));
 const html=skillArchiveView({data:validateSkillArchive(d),offset:0});
 assert.match(html,/不同新本文 1 個 · 重複 15 筆/);assert.match(html,/重複本文（P001）/);
 assert.equal(d.records.filter(r=>r.changed).length,16);
});
test('list plus exact Run lookup uses GET-only requests and rejects stale service/Run replies',async()=>{
 const calls=[];let service='one';
 const request=async path=>{calls.push(path);if(path.includes('?'))return {schemaVersion:1,historyOnly:true,offset:0,limit:20,total:1,runs:[{id:'RUN-one',task:'gepa-evolution'}]};return fixture(path.split('/').at(-1));};
 const c=new SkillArchiveClient({request,service:()=>service});assert.equal(await c.load(),true);assert.equal(c.data.runId,'RUN-one');assert.equal(calls.length,2);
 assert.equal(await c.load(0,'','RUN-older'),true);assert.equal(c.data.runId,'RUN-older');
 service='two';assert.equal(c.snapshot().data,null);assert.equal(await c.load(),true);assert.equal(c.data.runId,'RUN-one');
 const pending=[];c.request=()=>new Promise(resolve=>pending.push(resolve));const old=c.load();service='three';pending[0]({schemaVersion:1,historyOnly:true,offset:0,limit:20,total:0,runs:[]});assert.equal(await old,false);assert.equal(c.snapshot().data,null);
 c.request=async path=>path.includes('?')?{schemaVersion:1,historyOnly:true,offset:0,limit:20,total:1,runs:[{id:'RUN-one',task:'gepa-evolution'}]}:fixture('RUN-wrong');
 assert.equal(await c.load(),false);assert.match(c.error,/Run 不符/);
});
