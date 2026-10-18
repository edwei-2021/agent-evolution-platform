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
 if(!changed)return {ready:true,tone:'neutral',label:r.proposals===0?'未產生候選・尚未完成有效比較':'已探索候選・沿用基準',detail:r.proposals===0?'本輪沒有產生候選，無法判斷新 Skill 的成效。請檢查訓練覆蓋、略過與停止原因。':`產生 ${r.proposals} 個候選提案，最後仍選定基準 Skill；提案數不等於演化成果。`};
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
 ${ready&&r.taskFailures?.length?`<details class="task-failures"><summary>單題呼叫額度耗盡：${r.taskFailures.length} 次，均計 0 分</summary><p class="body-copy">以下單題未完成 SDK 修復；保留 max_iterations 與測試證據。整輪已完成其餘評測與審查，單題失敗不代表修復成功。</p><ul>${r.taskFailures.map(f=>`<li>${esc(f.rolloutId)} · ${esc(f.taskId)} · ${esc(({search:'搜尋',baseline:'基準獨立評測',selected:'選定 Skill 獨立評測'})[f.stage])} · ${esc(f.reason)}</li>`).join('')}</ul></details>`:''}
 ${ready&&r.validationScores?.[0]===1&&!r.eligible?'<p class="body-copy"><strong>基準在搜尋驗證已滿分，成功題數沒有更高分可比較。</strong> 這不能證明全部訓練題都已測過，或 Skill 沒有改善空間。目前以整題是否全部通過計 0／1 分；呼叫減少或少試幾次均不會提高這個分數。請檢閱訓練覆蓋、候選差異與停止原因，再用獨立的新題庫版本校準難度。</p>':''}
 ${r?.exploration?`<div class="small-notice" data-gepa-exploration><strong>多候選探索紀錄</strong> · seed ${esc(r.exploration.seed)}<br>訓練覆蓋 ${r.exploration.trainingTested}/${r.exploration.trainingTotal} 題 · 生成提案 ${r.exploration.generated} 個 · 不同新本文 ${r.exploration.uniqueNew} 個 · 重複本文 ${r.exploration.duplicates} 個 · 進入搜尋驗證 ${r.exploration.validatedNew} 個。${r.exploration.skippedDuplicates!==undefined?`<br>評測前攔下重複 ${r.exploration.skippedDuplicates} 次 · 省下候選訓練評測 ${r.exploration.savedCandidateEvaluations} 次。`:''}<br>完整本文、Parent、策略、差異、接受／淘汰與停止條件可在下方紀錄或「Skill 產生紀錄」查詢。候選保存與正式核准分別計算。</div>`:''}
 <div class="gepa-verdicts"><div><span>執行流程</span><strong>${esc(LIVE_STATUSES[run.status]||run.status)}</strong><small>${ready?'評估與審查均已完成':'流程完成後才確認成果'}</small></div><div><span>Skill 內容</span><strong>${ready?(r.selectedSkill.hash===r.baselineSkill.hash?'與基準相同':'已產生變更'):'待確認'}</strong><small>${ready?`候選提案 ${r.proposals} 個`:'尚未完成獨立審查'}</small></div><div><span>版本啟用狀態</span><strong>${esc(activation)}</strong><small>改善成立與版本啟用分別確認</small></div></div>
 ${ready?`<div class="table-wrap"><table class="gepa-score-table"><caption>實際演化成效比較（選定 Skill − 基準）</caption><thead><tr><th>評測資料</th><th>基準</th><th>選定 Skill</th><th>改善幅度</th></tr></thead><tbody>${rows}</tbody></table></div><p class="body-copy">模型呼叫 ${esc(r.calls)} / ${esc(run.gepaConfig.callBudget)} 次 · rollout ${esc(r.rollouts)} 次 · 搜尋評測 ${esc(r.metricEvaluations)} 次。${r.selectedSkill.hash===r.baselineSkill.hash?'同一 Skill 的分數差異不視為新技能演化。':''}</p>`:''}
 ${ready&&r.breakdown?`<details><summary>依難度與題目面向查看成效</summary>${['difficulty','topic'].map(dim=>`<div class="table-wrap"><table><thead><tr><th>${dim==='difficulty'?'難度':'題目面向'}</th><th>基準：驗證／最終</th><th>選定：驗證／最終</th></tr></thead><tbody>${Object.entries(r.breakdown[dim]||{}).map(([key,m])=>`<tr><td>${esc(({easy:'初階',medium:'中階',hard:'進階'})[key]||key)}</td>${['baseline','selected'].map(label=>`<td>${m[label].validation.total?`${m[label].validation.passed}/${m[label].validation.total}`:"無題目"} ／ ${m[label].heldout.total?`${m[label].heldout.passed}/${m[label].heldout.total}`:"無題目"}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`).join('')}</details>`:''}
 <p class="gepa-result-source">來源：<code>${esc(run.id)}</code> · ${run.gepaConfig?.profile==='bank'?`多難度題庫 v${run.gepaConfig.bankRevision}`:run.gepaConfig?.profile==='full'?'Full':'Smoke'}${duration}<br>結果適用於本輪合成任務；尚無跨資料集的效果證據。${runtime.error?'目前連線已過期，以上為保留的歷史結果。':''}</p>
 </section>`;
}
