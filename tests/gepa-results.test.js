import test from 'node:test';
import assert from 'node:assert/strict';
import {gepaOutcome,gepaResultsView} from '../dist/js/gepa-results-view.js';
import {gepaView} from '../dist/js/gepa-view.js';

// Synthetic presentation fixtures only: no model calls or private run artifacts.
const skill=(hash,body)=>({name:'python-fix-and-verify',description:'Bounded repair.',hash:hash.repeat(64),body});
function fixture(){
 const baseline=skill('a','Read, repair, verify.');
 const run={id:'RUN-results-fixture',status:'completed',createdAt:'2026-01-01T00:00:00Z',updatedAt:'2026-01-01T00:02:05Z',events:[],agents:[],
  gepaConfig:{baseline:{id:'GSV-baseline',skill:baseline},profile:'smoke',callBudget:162,metricBudget:8,counts:{train:4,validation:2,heldout:4}},
  gepaResult:{checksPassed:true,eligible:false,baselineSkill:baseline,selectedSkill:structuredClone(baseline),proposals:0,validationScores:[1],calls:40,rollouts:17,metricEvaluations:5,
   final:{baseline:{validation:{passed:2,total:2},heldout:{passed:4,total:4}},selected:{validation:{passed:2,total:2},heldout:{passed:4,total:4}}}}};
 const workspace={activeVersionId:'GSV-baseline',active:{skill:baseline},versions:[{id:'GSV-baseline',label:'G0',runId:null}],runs:[{id:run.id,status:run.status,createdAt:run.createdAt}],latestRun:run,sdk:{available:true},optimizer:{available:true,version:'0.1.4'}};
 return {data:{gepa:workspace},capabilities:{},enabled:true};
}
function improving(runtime){
 const r=runtime.data.gepa.latestRun.gepaResult;
 r.selectedSkill=skill('b','Verify boundaries and repair.');r.eligible=true;r.proposals=1;
 r.final.baseline.validation.passed=1;r.final.baseline.heldout.passed=3;
 return r;
}
const approval=html=>html.match(/<button[^>]*data-gepa-approve[^>]*>/)[0];

test('difficulty breakdown labels absent samples and retains the frozen bank identity',()=>{
 const runtime=fixture(),run=runtime.data.gepa.latestRun;
 run.gepaConfig.profile='bank';run.gepaConfig.bankRevision=7;
 const zero={passed:0,total:0},two={passed:2,total:2};
 run.gepaResult.breakdown={difficulty:{easy:{baseline:{validation:zero,heldout:two},selected:{validation:zero,heldout:two}}},topic:{}};
 const html=gepaResultsView(runtime);assert.match(html,/依難度與題目面向/);assert.match(html,/初階/);assert.match(html,/無題目 ／ 2\/2/);assert.match(html,/多難度題庫 v7/);
});

test('completed perfect seed visibly reports zero evolution before settings, rather than generic success',()=>{
 const runtime=fixture(),html=gepaView(runtime);
 assert.match(html,/實際演化成果：未產生新 Skill・沿用基準/);
 assert.match(html,/候選提案為 0/);assert.match(html,/候選提案 0 個/);
 assert.match(html,/2 \/ 2（100%）/);assert.match(html,/4 \/ 4（100%）/);
 assert.equal((html.match(/0 題 · 0 個百分點/g)||[]).length,2);
 assert.match(html,/未開放核准・維持現行版本/);assert.match(approval(html),/disabled/);
 assert.ok(html.indexOf('data-gepa-results')<html.indexOf('搜尋設定'));
 assert.match(html,/耗時 2 分 5 秒/);assert.match(html,/本輪合成任務/);
});
test('changed improving skill shows measured gains separately from manual activation',()=>{
 const runtime=fixture();improving(runtime);const html=gepaView(runtime);
 assert.match(html,/已驗證改善・通過演化門檻/);assert.match(html,/\+1 題 · \+50 個百分點/);
 assert.match(html,/\+1 題 · \+25 個百分點/);assert.match(html,/待人工核准・尚未啟用/);
 assert.ok(!approval(html).includes('disabled'));
});
test('held-out regression and unchanged validation cannot be presented as successful evolution',()=>{
 for(const scenario of ['heldout','validation']){
  const runtime=fixture(),r=improving(runtime);r.eligible=false;
  if(scenario==='heldout')r.final.selected.heldout.passed=2;else r.final.selected.validation.passed=1;
  const html=gepaView(runtime);
  assert.match(html,/未通過演化門檻|驗證未改善/);assert.doesNotMatch(html,/已驗證改善/);
  assert.match(approval(html),/disabled/);
  if(scenario==='heldout')assert.match(html,/-1 題 · -25 個百分點/);
 }
});
test('unchanged skill with variable replay scores still does not claim a new evolved skill',()=>{
 const runtime=fixture();runtime.data.gepa.latestRun.gepaResult.final.baseline.validation.passed=1;
 const html=gepaResultsView(runtime);
 assert.match(html,/未產生新 Skill/);assert.match(html,/同一 Skill 的分數差異不視為新技能演化/);
 assert.match(html,/\+50 個百分點/);assert.doesNotMatch(html,/已驗證改善/);
});
test('rejected proposals are distinct from the number of accepted evolved skills',()=>{
 const runtime=fixture();runtime.data.gepa.latestRun.gepaResult.proposals=2;
 const html=gepaResultsView(runtime);
 assert.match(html,/產生 2 個候選提案，最後仍選定基準 Skill/);assert.match(html,/未產生新 Skill/);
});
test('partial, failed and interrupted results never unlock approval or final improvement claims',()=>{
 for(const status of ['queued','running','failed','cancelled','interrupted']){
  const runtime=fixture();improving(runtime);runtime.data.gepa.latestRun.status=status;
  const html=gepaView(runtime),panel=gepaResultsView(runtime);
  assert.equal(gepaOutcome(runtime.data.gepa.latestRun).ready,false);
  assert.doesNotMatch(panel,/已驗證改善|已完成獨立審查|gepa-score-table/);
  assert.match(html,/不[可]核准/);assert.match(approval(html),/disabled/);
 }
});
test('completed status without reviewed evidence remains pending',()=>{
 const runtime=fixture();delete runtime.data.gepa.latestRun.gepaResult.checksPassed;
 assert.equal(gepaOutcome(runtime.data.gepa.latestRun).ready,false);
 assert.match(gepaResultsView(runtime),/尚無最終結論/);
 assert.match(approval(gepaView(runtime)),/disabled/);
});
test('activation and rollback labels follow persisted versions and the current baseline',()=>{
 const runtime=fixture(),w=runtime.data.gepa;improving(runtime);
 w.activeVersionId='GSV-other';assert.match(gepaResultsView(runtime),/目前基準已變更/);
 assert.match(approval(gepaView(runtime)),/disabled/);
 w.versions.push({id:'GSV-approved',runId:w.latestRun.id});
 assert.match(gepaResultsView(runtime),/已核准，目前使用其他版本/);
 w.activeVersionId='GSV-approved';assert.match(gepaResultsView(runtime),/已核准並啟用/);
 assert.match(approval(gepaView(runtime)),/disabled/);
});
test('selected historical run owns its result, denominator and source even if latest run improves',()=>{
 const runtime=fixture();runtime.selectedGepaRun=structuredClone(runtime.data.gepa.latestRun);
 runtime.selectedGepaRun.id='RUN-older';runtime.data.gepa.latestRun.id='RUN-newer';improving(runtime);
 runtime.gepaProfile='full';const html=gepaResultsView(runtime);
 assert.match(html,/RUN-older/);assert.doesNotMatch(html,/RUN-newer|已驗證改善/);
 assert.match(html,/Smoke/);assert.match(html,/4 \/ 4（100%）/);
 runtime.error='snapshot disconnected';assert.match(gepaResultsView(runtime),/保留的歷史結果/);
});
test('empty and escaped source states are readable without injecting markup',()=>{
 assert.match(gepaResultsView({}),/尚無實驗結果/);
 const runtime=fixture();runtime.data.gepa.latestRun.id='<img src=x onerror=alert(1)>';
 const html=gepaResultsView(runtime);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
});
