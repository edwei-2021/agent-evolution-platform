import {escapeHtml as esc} from './agent-view.js';
import {LIVE_STATUSES} from './runtime-client.js';
const roles={coordinator:'準備與凍結設定',worker:'執行基準',reflector:'訓練反思',evaluator:'評估候選',reviewer:'驗證證據'};
const seconds=v=>`${Math.max(0,Math.floor(Number(v)||0))} 秒`;
export function completedCalls(progress){return progress?.completedCalls??Math.max(0,(progress?.calls||0)-(progress?.lastCall?.status==='running'||progress?.lastCall?.status==='failed'||progress?.lastCall?.status==='cancelled'?1:0));}
export function runProgressView(runtime,run){
 const active=run&&['queued','running'].includes(run.status),stale=!!runtime.error||runtime.enabled===false;
 const stages=run?.agents||[],done=stages.filter(a=>a.status==='completed').length,total=stages.length||5;
 const current=stages.find(a=>a.status==='running'),p=run?.llmProgress,call=p?.lastCall;
 const now=Date.parse(runtime.data?.serverTime||runtime.lastSuccess||run?.updatedAt);
 const end=Date.parse(run?.endedAt),clock=Number.isFinite(end)?end:now;
 const elapsed=run?run.executionProgress?.elapsedSeconds??Math.max(0,(clock-Date.parse(run.createdAt))/1000):0;
 const callEnd=call?.finishedAt??clock/1000;
 const callElapsed=call?.startedAt?Math.max(0,callEnd-call.startedAt):0;
 const waiting=active&&call?.status==='running',remaining=waiting?Math.max(0,(call.deadlineEpoch||0)-clock/1000):0;
 const status=stale?'更新已暫停／快照過期':run?LIVE_STATUSES[run.status]:'等待開始';
 const note=waiting?(call.chunks>0?`已收到 ${call.chunks} 段回應 · 答案 ${call.outputChars||0} 字元 · reasoning ${call.reasoningChars||0} 字元`:'等待模型首段回應；目前無法判定是載入、排隊或推論'):
   run?.status==='completed'?'流程已完成；呼叫預算可以不必全部用完':run?.status==='cancelled'?'已取消；不再送出後續模型請求':run?.status==='failed'?'流程失敗；請檢查下方原因與 log':run?.status==='interrupted'?'流程已中斷；請重新開始一輪':'後端會依序執行各角色';
 const model=run?.task==='llm-evolution';
 return `<section class="card spaced execution-progress" data-execution-progress aria-label="實驗進度">
 <div class="progress-title"><h2>實驗進度</h2><span class="progress-status" role="status">${active&&!stale?'<i class="progress-spinner" aria-hidden="true"></i>':''}${esc(status)}</span></div>
 <div class="progress-details"><span>已完成角色階段 · ${esc(current?roles[current.role]||current.role:run?.status==='completed'?'完成':run?.llmProgress?.phase||run?.skillProgress?.phase||'等待')}</span><strong>${done} / ${total}</strong></div>
 <progress value="${done}" max="${total}" aria-label="已完成角色階段"></progress>
 <p class="body-copy">整輪已用 ${seconds(elapsed)}${run?.llmConfig?` · 上限 ${seconds(run.llmConfig.maxSeconds)}`:''} · 最近後端心跳 ${esc(run?.executionProgress?.heartbeatAt||run?.updatedAt||'尚無')}<br>最近成功 polling ${esc(runtime.lastSuccess||'尚無')}${stale?' · 此頁暫停更新，不代表後端已停止':''}</p>
 ${model?`<div class="progress-details"><span>已完成模型呼叫（上限預算）</span><strong>${completedCalls(p)} / ${run.llmConfig.callBudget}</strong></div><progress value="${completedCalls(p)}" max="${run.llmConfig.callBudget}" aria-label="已完成模型呼叫"></progress>
 <p class="body-copy">已送出 ${p?.calls||0} 次 · 失敗 ${p?.failedCalls||0} 次${call?` · 目前／最近 #${call.id} · ${esc(call.split||call.kind)} ${esc(call.taskId||'')}<br>本次已用 ${seconds(callElapsed)} · 單次上限 ${seconds(call.timeoutSeconds||run.llmConfig.callTimeoutSeconds||run.llmConfig.provider.config.inferenceTimeout)}${waiting?` · 剩餘 ${seconds(remaining)}`:''}`:''}</p>
 ${waiting&&!stale?'<progress class="model-wait" aria-label="等待模型回應"></progress>':''}`:''}
 <p class="progress-note">${esc(note)}${waiting&&callElapsed>=30?'。等待較久；可取消，或在下一輪調整單次上限。':''}</p>
 ${call?.lastChunkAt?`<p class="body-copy">最近模型回應：${esc(new Date(call.lastChunkAt*1000).toISOString())}</p>`:''}
 ${run?.error||call?.error?`<div class="error-banner" role="alert">${esc(run.error||call.error)}</div>`:''}
 </section>`;
}
