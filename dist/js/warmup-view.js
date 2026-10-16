import {escapeHtml as esc} from './agent-view.js';
const statuses={RUNNING:'暖機中',PRELOAD_PASS:'暖機成功紀錄',FAIL:'暖機失敗',CANCELLED:'已取消',INTERRUPTED:'服務重啟，中斷狀態未確認'};
export function warmupView(provider,{disabled=false,stale=false}={}){
 const strata=provider?.config?.provider==='strata';
 const job=provider?.warmup,active=job?.status==='RUNNING',same=job&&job.revision===provider.revision&&job.config?.model===provider.config?.model;
 return `<section class="card spaced" data-warmup-panel><div class="card-heading"><div><h2>模型暖機</h2><p>先預先載入已儲存模型，再開始實驗；暖機不計入 15／101 次呼叫預算。</p></div><a href="#logs">查看模組 Log ↗</a></div>
 <p class="body-copy">模型：<code>${esc(provider?.config?.model||'尚未讀取或設定')}</code> · 暖機上限 ${provider?.config?.inferenceTimeout||'—'} 秒（框架整合的 Inference timeout） · ${strata?'使用 Strata 載入 API；模型保留由 Strata 管理。<br>成功紀錄代表該次載入完成，尚未驗證推論。':'要求保留 15 分鐘。<br>成功紀錄代表該次載入完成；Ollama 之後仍可能卸載模型，請接著開始實驗。'}</p>
 <div class="actions card-actions"><button type="button" class="button secondary" data-model-warmup ${disabled||stale||provider?.busy||!provider?.config?.model?'disabled':''}>預先載入模型</button>${active?`<button type="button" class="button danger" data-model-warmup-cancel="${esc(job.id)}" ${disabled||stale?'disabled':''}>取消暖機</button>`:''}<span role="status">${esc(stale?'紀錄過期／更新已暫停':job?statuses[job.status]||job.status:'尚無暖機紀錄')}</span></div>
 ${job?`<div class="small-notice">${esc(job.config?.model)} · ${same?'目前模型設定':'先前模型設定'} · 已用 ${Math.floor(job.elapsedSeconds||0)} 秒／上限 ${job.timeoutSeconds} 秒<br>開始 ${esc(job.startedAt)}${job.finishedAt?` · 結束 ${esc(job.finishedAt)}`:''}${job.loadDurationMs!==undefined?`<br>Ollama 回報載入 ${job.loadDurationMs} ms；本機總耗時 ${job.elapsedMs} ms`:''}<br><code>${esc(job.id)}</code></div>${active&&!stale?'<progress class="model-wait" aria-label="等待模型暖機完成"></progress>':''}${job.error?`<div class="error-banner" role="alert">${esc(job.error)}</div>`:''}`:''}</section>`;
}
