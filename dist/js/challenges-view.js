import {escapeHtml as esc} from './agent-view.js';
const levels={easy:'初階',medium:'中階',hard:'進階'},splits={train:'訓練／反思',validation:'驗證／選擇',heldout:'最終測試'};
export function challengesView(state){
 const d=state.draft,data=state.data,disabled=state.busy?'disabled':'';
 const field=(name,label,type='text')=>`<label>${label}<input name="${name}" type="${type}" value="${esc(d[name])}" required ${disabled}></label>`;
 const area=(name,label,rows=6)=>`<label>${label}<textarea name="${name}" rows="${rows}" required spellcheck="false" ${disabled}>${esc(d[name])}</textarea></label>`;
 const select=(name,label,options)=>`<label>${label}<select name="${name}" ${disabled}>${Object.entries(options).map(([k,v])=>`<option value="${k}" ${d[name]===k?'selected':''}>${v}</option>`).join('')}</select></label>`;
 const counts=Object.keys(splits).map(s=>`${splits[s]} ${data?.questions.filter(q=>q.enabled&&q.split===s).length??0}`).join(' / ');
 return `<div class="page-heading"><div><p class="eyebrow">VERSIONED PYTHON CHALLENGE BANK</p><h1>多難度 Python 題庫</h1><p>管理真實修復題、錯誤起始碼與評測；每輪 GEPA 凍結題庫快照。</p></div><div class="actions"><button class="button secondary" data-bank-refresh ${disabled}>更新題庫</button><button class="button primary" data-bank-new ${!data||state.busy?'disabled':''}>新增題目</button></div></div>
 <div class="demo-banner"><span class="info-icon">i</span><div><strong>12 題研究啟發的原創修復挑戰 · 三種難度</strong><span>參考 EvalPlus 的完整測試與 BigCodeBench 的多面向設計；並非其官方題目或成績。難度為作者標籤，仍須依模型實測。<br>本頁管理題目；儲存或換頁不會開始模型實驗。按「準備題庫演化」會選取題庫，再按「開始題庫演化」才提交。<br>既有 Run 保留原快照。每個分割至少啟用 2 題；相近題目的群組不可跨分割。</span></div><button class="button primary" data-bank-gepa>準備題庫演化 →</button></div>
 ${state.error?`<p class="error-banner spaced" role="alert">${esc(state.error)}</p>`:''}
 <section class="card spaced"><div class="card-heading"><div><h2>題目清單</h2><p>題庫版本 ${esc(data?.revision??'待載入')} · 共 ${data?.questions.length??0} 題 · 已啟用：${counts}</p></div><label>難度篩選<select data-bank-filter><option value="all">全部難度</option>${Object.entries(levels).map(([k,v])=>`<option value="${k}" ${state.filter===k?'selected':''}>${v}</option>`).join('')}</select></label></div>
 <div class="table-wrap"><table><thead><tr><th>題目</th><th>面向／難度</th><th>分割／啟用</th><th>測試數</th><th>操作</th></tr></thead><tbody>${(data?.questions||[]).filter(q=>state.filter==='all'||q.difficulty===state.filter).map(q=>`<tr><td><button class="text-button" data-bank-select="${esc(q.id)}">${esc(q.title)}</button></td><td>${esc(q.topic)} · ${levels[q.difficulty]}</td><td>${splits[q.split]} · ${q.enabled?'啟用':'停用'}</td><td>公開 ${q.visible.length}／保留 ${q.hidden.length}</td><td><button class="button secondary" data-bank-select="${esc(q.id)}" ${disabled}>編輯</button><button class="button danger" data-bank-delete="${esc(q.id)}" ${disabled}>刪除</button></td></tr>`).join('')||'<tr><td colspan="5">尚無符合篩選的題目。</td></tr>'}</tbody></table></div></section>
 ${d?`<section class="card spaced bank-editor"><h2>${state.selectedId?'編輯題目':'新增題目'}</h2><p class="body-copy">固定入口 <code>solve(data)</code>，輸入與輸出使用 JSON。支援受限迴圈、串列、字典、集合及資料方法；禁止 import、任意屬性、檔案、網路、shell、類別與遞迴。每題每組 2–20 筆測試。儲存時會在有 CPU／記憶體／時間限制的獨立評測程式驗證參考解答，且要求起始碼確實有錯。</p>
 <form id="challenge-form"><div class="bank-fields">${field('title','題目名稱')}${field('topic','題目面向')}${field('group','相近題目群組（同群組不可跨資料分割）')}${select('difficulty','難度',levels)}${select('split','資料分割',splits)}<label class="bank-enabled"><input name="enabled" type="checkbox" ${d.enabled?'checked':''} ${disabled}>啟用於未來 GEPA 實驗</label></div>
 ${area('prompt','任務要求（請寫一般行為與邊界條件，避免直接附解答）',5)}
 <div class="two-col">${area('baseline','錯誤的起始 Python 程式',12)}${area('reference','參考解答（僅供題庫驗證，不提供給模型）',12)}</div>
 <p class="body-copy">測試格式：<code>{"input": ..., "expected": ...}</code>；預期例外使用 <code>{"input": ..., "raises": "ValueError"}</code>。輸入不可被修改；有限浮點數使用固定 1e-9 容差。</p>
 <div class="two-col">${area('visible','公開測試 JSON',12)}${area('hidden','保留測試 JSON（工具不能存取）',12)}</div>
 <label>研究／來源連結（每行一個 HTTPS，可留空）<textarea name="sources" rows="3" ${disabled}>${esc(d.sources)}</textarea></label>${area('attribution','來源與改編說明',2)}
 <div class="actions card-actions"><button class="button primary" type="submit" ${disabled}>${state.busy?'驗證並儲存中…':'驗證並儲存題目'}</button><span>修改僅影響之後提交的實驗。</span></div></form></section>`:'<section class="card spaced"><p class="body-copy">點選題目檢閱或編輯；也可新增題目。要讓 GEPA 使用此題庫，請在 GEPA 頁選擇「多難度題庫」。</p></section>'}`;
}
