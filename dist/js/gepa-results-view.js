import {escapeHtml as esc} from './agent-view.js';
import {LIVE_STATUSES} from './runtime-client.js';

const number=n=>Number(n.toFixed(1)).toString();
const signed=n=>`${n>0?'+':''}${number(n)}`;
const rate=m=>100*m.passed/m.total;
const score=m=>`${m.passed} / ${m.total}（${number(rate(m))}%）`;
export function gepaOutcome(run){
 const r=run?.gepaResult;
 if(run?.status!=='completed'||r?.checksPassed!==true)return {ready:false,tone:run&&['failed','cancelled','interrupted'].includes(run.status)?'error':'pending',label:run&&['failed','cancelled','interrupted'].includes(run.status)?'未完成，無可確認的演化成果':'待完成評估與審查',detail:'依此 Run 的完整評估與審查確認成果。'};
 const changed=r.selectedSkill.hash!==r.baselineSkill.hash;
 const validation=r.final.selected.validation.passed-r.final.baseline.validation.passed;
 const heldout=r.final.selected.heldout.passed-r.final.baseline.heldout.passed;
 if(!changed)return {ready:true,tone:'neutral',label:'未產生新 Skill・沿用基準',detail:r.proposals===0?(r.validationScores?.[0]===1?'基準在搜尋驗證已達滿分；本輪候選提案為 0，最後沿用原 Skill。':'本輪候選提案為 0，最後沿用原 Skill。'):`產生 ${r.proposals} 個候選提案，最後仍選定基準 Skill；提案數不等於演化成果。`};
 if(r.eligible)return {ready:true,tone:'success',label:'已驗證改善・通過演化門檻',detail:'選定 Skill 已變更，獨立驗證改善，最終測試未退步。'};
 return {ready:true,tone:'error',label:heldout<0?'候選退步・未通過演化門檻':validation<=0?'Skill 有變更・驗證未改善':'未通過演化門檻',detail:'保留量測結果與 Skill 差異，維持目前版本。'};
}

export function gepaResultsView(runtime){
 const w=runtime.data?.gepa,run=runtime.selectedGepaRun||w?.latestRun;
 if(!run)return '<section class="card spaced gepa-results" data-gepa-results><h2>實際演化成果</h2><p class="body-copy">尚無實驗結果。完成流程後，會分別顯示技能改善與啟用狀態。</p></section>';
 const result=gepaOutcome(run),r=run.gepaResult,ready=result.ready;
 const version=w?.versions?.find(v=>v.runId===run.id);
 const activation=version?(version.id===w.activeVersionId?'已核准並啟用':'已核准，目前使用其他版本'):!ready?'尚未確認':!r.eligible?'未開放核准・維持現行版本':run.gepaConfig.baseline.id!==w?.activeVersionId?'目前基準已變更・需重新實驗':'待人工核准・尚未啟用';
 const start=Date.parse(run.createdAt),end=Date.parse(run.endedAt||run.updatedAt),seconds=Math.max(0,Math.round((end-start)/1000));
 const duration=Number.isFinite(seconds)&&!['queued','running'].includes(run.status)?` · 耗時 ${Math.floor(seconds/60)} 分 ${seconds%60} 秒`:'';
 const rows=ready?['validation','heldout'].map(split=>{
  const before=r.final.baseline[split],after=r.final.selected[split],delta=after.passed-before.passed,points=rate(after)-rate(before);
  return `<tr><th scope="row">${split==='validation'?'獨立驗證':'最終測試'}</th><td>${esc(score(before))}</td><td>${esc(score(after))}</td><td class="gepa-gain ${delta>0?'positive':delta<0?'negative':''}">${signed(delta)} 題 · ${signed(points)} 個百分點</td></tr>`;
 }).join(''):'';
 return `<section class="card spaced gepa-results outcome-${result.tone}" data-gepa-results aria-labelledby="gepa-results-title">
 <div class="gepa-results-heading"><div><p class="eyebrow">本輪成果判讀</p><h2 id="gepa-results-title">實際演化成果：${esc(result.label)}</h2></div><span class="gepa-result-badge">${ready?'已完成獨立審查':'尚無最終結論'}</span></div>
 <p class="body-copy">${esc(result.detail)}</p>
 <div class="gepa-verdicts"><div><span>執行流程</span><strong>${esc(LIVE_STATUSES[run.status]||run.status)}</strong><small>${ready?'評估與審查均已完成':'流程完成後才確認成果'}</small></div><div><span>Skill 內容</span><strong>${ready?(r.selectedSkill.hash===r.baselineSkill.hash?'與基準相同':'已產生變更'):'待確認'}</strong><small>${ready?`候選提案 ${r.proposals} 個`:'尚未完成獨立審查'}</small></div><div><span>版本啟用狀態</span><strong>${esc(activation)}</strong><small>改善成立與版本啟用分別確認</small></div></div>
 ${ready?`<div class="table-wrap"><table class="gepa-score-table"><caption>實際演化成效比較（選定 Skill − 基準）</caption><thead><tr><th>評測資料</th><th>基準</th><th>選定 Skill</th><th>改善幅度</th></tr></thead><tbody>${rows}</tbody></table></div><p class="body-copy">模型呼叫 ${esc(r.calls)} / ${esc(run.gepaConfig.callBudget)} 次 · rollout ${esc(r.rollouts)} 次 · 搜尋評測 ${esc(r.metricEvaluations)} 次。${r.selectedSkill.hash===r.baselineSkill.hash?'同一 Skill 的分數差異不視為新技能演化。':''}</p>`:''}
 <p class="gepa-result-source">來源：<code>${esc(run.id)}</code> · ${run.gepaConfig?.profile==='full'?'Full':'Smoke'}${duration}<br>結果適用於本輪合成任務；尚無跨資料集的效果證據。${runtime.error?'目前連線已過期，以上為保留的歷史結果。':''}</p>
 </section>`;
}
