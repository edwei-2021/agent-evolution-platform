import test from 'node:test';
import assert from 'node:assert/strict';
import {initialRegistry} from '../dist/js/agents.js';
import {validateGepaRun} from '../dist/js/runtime-client.js';
import {COMPARISON_POLICY} from '../dist/js/gepa-comparison.js';
import {gepaResultsView,gepaOutcome} from '../dist/js/gepa-results-view.js';
import {gepaView} from '../dist/js/gepa-view.js';

function fixture(){
 const stamp='2026-10-21T00:00:00Z',skill=hash=>({name:'python-fix-and-verify',description:'Repair.',body:hash,hash:hash.repeat(64)});
 const data=Object.fromEntries(['validation','heldout'].map(s=>[s,Array.from({length:3},(_,i)=>({id:`CH-${s}-${i}`,group:`${s}-${i}`,difficulty:'hard',topic:'parsing'}))]));
 const tasks=Object.entries(data).flatMap(([split,rows],s)=>rows.map((t,i)=>({taskId:t.id,split,group:t.group,difficulty:t.difficulty,topic:t.topic,baseline:i===0?1:0,selected:i===0?0:1,outcome:i===0?'regressed':'improved',baselineRolloutId:`R${String(s*6+i+1).padStart(4,'0')}`,selectedRolloutId:`R${String(s*6+i+4).padStart(4,'0')}`})));
 return {id:'RUN-paired',task:'gepa-evolution',mode:'native-tools',status:'completed',createdAt:stamp,updatedAt:stamp,endedAt:stamp,events:[],artifacts:[],agents:initialRegistry().agents.map(a=>({...a,status:'completed',pid:123,processAlive:false,updatedAt:stamp,logTail:''})),
  gepaConfig:{engine:'gepa-nanobot-repair-v1',sdk:{version:'0.3.5'},optimizer:{version:'0.1.4'},baseline:{id:'GSV-baseline',skill:skill('a')},profile:'bank',bankRevision:2,datasetSnapshot:{version:'python-challenges-v3',revision:2,data},counts:{train:6,validation:3,heldout:3},metricBudget:10,callBudget:133,provider:{config:{model:'local'}},comparisonPolicy:COMPARISON_POLICY},
  gepaResult:{engine:'gepa-nanobot-repair-v1',checksPassed:true,eligible:false,selectedSkill:skill('b'),baselineSkill:skill('a'),evidenceHash:'c'.repeat(64),calls:56,metricEvaluations:10,rollouts:22,proposals:1,
   final:{baseline:{validation:{passed:1,total:3},heldout:{passed:1,total:3}},selected:{validation:{passed:2,total:3},heldout:{passed:2,total:3}}},
   comparison:{policy:COMPARISON_POLICY,tasks,splits:Object.fromEntries(['validation','heldout'].map(s=>[s,{improved:2,regressed:1,'retained-pass':0,'retained-fail':0}]))},releaseBlockers:['validation-task-regressed','heldout-task-regressed']}};
}
const runtime=run=>({selectedGepaRun:run,enabled:true,capabilities:{},data:{gepa:{activeVersionId:'GSV-baseline',versions:[],sdk:{available:true},optimizer:{available:true}}}});

test('a net score gain with a lost pass is rejected and displayed beside exact task/rollout evidence',()=>{
 const run=validateGepaRun(fixture()),html=gepaView(runtime(run));
 assert.equal(gepaOutcome(run).tone,'error');assert.match(html,/逐題退步・未通過演化門檻/);
 for(const t of ['CH-validation-0','R0001 → R0004','仍未通過','最終測試有原本通過的題目退步'])assert.ok(html.includes(t));
 assert.match(html,/data-gepa-approve[^>]*disabled/);assert.doesNotMatch(html,/已驗證改善/);
});
test('client refuses missing, duplicated, relabeled, contradictory or falsely eligible pairs',()=>{
 const edits=[r=>r.gepaResult.eligible=true,r=>delete r.gepaResult.comparison,
  r=>r.gepaResult.comparison.tasks.pop(),r=>r.gepaResult.comparison.tasks[1].taskId=r.gepaResult.comparison.tasks[0].taskId,
  r=>r.gepaResult.comparison.tasks[1].selectedRolloutId='R0001',r=>r.gepaResult.comparison.tasks[0].group='edited',
  r=>r.gepaResult.comparison.tasks[0].split='train',r=>r.gepaResult.comparison.tasks[0].baseline=true,
  r=>r.gepaResult.comparison.tasks[0].outcome='improved',r=>r.gepaResult.comparison.splits.validation.regressed=0,
  r=>r.gepaResult.final.selected.heldout.passed=3,r=>r.gepaResult.releaseBlockers=[],
  r=>r.gepaConfig.comparisonPolicy='unknown',r=>delete r.gepaConfig.comparisonPolicy];
 for(const edit of edits){const run=fixture();edit(run);assert.throws(()=>validateGepaRun(run));}
});
test('legacy aggregate results keep their recorded verdict without inventing paired evidence',()=>{
 const run=fixture();delete run.gepaConfig.comparisonPolicy;delete run.gepaResult.comparison;delete run.gepaResult.releaseBlockers;run.gepaResult.eligible=true;
 validateGepaRun(run);const html=gepaResultsView(runtime(run));
 assert.match(html,/已驗證改善/);assert.match(html,/此歷史結果採總分判定/);assert.doesNotMatch(html,/data-gepa-paired/);
});
test('incomplete runs cannot display confirmed paired outcomes from a partial saved result',()=>{
 for(const status of ['running','failed','cancelled','interrupted']){
  const run=fixture();run.status=status;const html=gepaResultsView(runtime(run));
  assert.doesNotMatch(html,/data-gepa-paired|已完成獨立審查/);
 }
});
test('unchanged Skill and task names remain truthful and escaped',()=>{
 const run=fixture();run.gepaResult.selectedSkill=run.gepaResult.baselineSkill;
 run.gepaResult.releaseBlockers.unshift('unchanged-skill');validateGepaRun(run);
 assert.match(gepaResultsView(runtime(run)),/同一 Skill 的分數差異不視為新技能演化/);
 run.gepaResult.comparison.tasks[0].topic='<img src=x onerror=alert(1)>';
 const html=gepaResultsView(runtime(run));assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
});
