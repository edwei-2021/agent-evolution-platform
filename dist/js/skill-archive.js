import {escapeHtml as esc} from './agent-view.js';
const tasks={'gepa-evolution':'GEPA Python Skill','llm-evolution':'LLM 文字 Skill','skill-evolution':'本機規則 Skill'};
const id=s=>typeof s==='string'&&/^RUN-[A-Za-z0-9-]+$/.test(s);
export function validateSkillArchive(value){
 const text=s=>s===null||typeof s==='string'&&new TextEncoder().encode(s).length<=16000;
 if(value?.schemaVersion!==1||!id(value.runId)||!Object.hasOwn(tasks,value.task)||value.historyOnly!==true||!Array.isArray(value.records)||value.records.length>32||!Array.isArray(value.warnings)||value.warnings.length>100||!Array.isArray(value.approvedVersions)||value.approvedVersions.length>100||!text(value.baseline?.text))throw Error('Skill 紀錄格式不正確');
 for(const r of value.records)if(!/^(P\d{3}|C\d{1,2}|T\d{4})$/.test(r.id)||!['started','returned','generated','failed','unknown'].includes(r.status)||!['recorded','reconstructed','recovered-response'].includes(r.origin)||!text(r.instruction?.text)||!text(r.parent?.text)||!(r.patch===null||typeof r.patch==='string'&&new TextEncoder().encode(r.patch).length<=36000)||!Array.isArray(r.trainingRefs)||r.trainingRefs.length>30||!r.conditions||typeof r.conditions!=='object')throw Error('Skill 提案紀錄不正確');
 return value;
}
export class SkillArchiveClient{
 constructor({request,onUpdate=()=>{},service=()=>null}){this.request=request;this.onUpdate=onUpdate;this.service=service;this.offset=0;this.task='';this.generation=0;this.busy=false;this.error=null;this.data=null;this.index=null;this.scope=service();}
 snapshot(){return this.scope===this.service()?this:{busy:false,error:'服務已切換，請重新查詢',data:null,index:null,offset:0,task:''};}
 async load(offset=0,task=this.task,runId=''){
  if(!Number.isInteger(offset)||offset<0||offset>100000||task!==''&&!Object.hasOwn(tasks,task)||runId&&!id(runId))throw Error('Skill 查詢條件不正確');
  const generation=++this.generation,scope=this.service();if(this.scope!==scope){this.data=null;this.index=null;}this.scope=scope;this.busy=true;this.error=null;this.onUpdate();
  try{
   const page=await this.request(`/api/v1/debug/skills?${new URLSearchParams({offset:String(offset),task})}`,{timeoutMs:30000});
   if(page.schemaVersion!==1||page.historyOnly!==true||page.offset!==offset||page.limit!==20||!Number.isInteger(page.total)||!Array.isArray(page.runs)||page.runs.length>20||page.runs.some(r=>!id(r.id)||!Object.hasOwn(tasks,r.task)))throw Error('Skill 實驗清單不正確');
   if(generation!==this.generation||scope!==this.service())return false;
   this.index=page;this.offset=offset;this.task=task;this.data=null;
   const selected=runId||page.runs[0]?.id;
   if(selected){const data=validateSkillArchive(await this.request(`/api/v1/debug/skills/${selected}`,{timeoutMs:30000}));if(data.runId!==selected)throw Error('Skill 與 Run 不符');if(generation!==this.generation||scope!==this.service())return false;this.data=data;}
   return true;
  }catch(e){if(generation===this.generation)this.error=e.message;return false;}
  finally{if(generation===this.generation){this.busy=false;this.onUpdate();}}
 }
}
const time=s=>{if(s===null||s===undefined)return '未知';const d=new Date(typeof s==='number'?s*1000:s);return Number.isNaN(d.getTime())?'未知':d.toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false});};
const code=s=>`<pre>${esc(s??'未保存')}</pre>`;
export function skillArchiveResults(state){
 const d=state.data;
 return `<div data-skill-archive-results>${state.error?`<p class="error-banner">${esc(state.error)}</p>`:''}${state.busy?'<p role="status">讀取已保存的 Skill 紀錄…</p>':''}
 <section class="card spaced"><h2>跨 Run 查詢</h2><div class="table-wrap"><table><thead><tr><th>Run</th><th>類型</th><th>狀態／建立時間</th></tr></thead><tbody>${(state.index?.runs||[]).map(r=>`<tr><td><button class="text-button" data-skill-archive-run="${esc(r.id)}">${esc(r.id)}</button></td><td>${esc(tasks[r.task])}</td><td>${esc(r.status)}<br>${esc(r.createdAt)}</td></tr>`).join('')||'<tr><td colspan="3">尚無查詢結果</td></tr>'}</tbody></table></div><p>共 ${esc(state.index?.total??0)} 個 Run · 每頁 20 個。提案、未選用及相同本文均保留；正式核准版本另外列出。</p><div class="actions"><button class="button secondary" data-skill-archive-page="${Math.max(0,state.offset-20)}" ${state.busy||state.offset===0?'disabled':''}>上一頁</button><button class="button secondary" data-skill-archive-page="${state.offset+20}" ${state.busy||state.offset+20>=(state.index?.total??0)?'disabled':''}>下一頁</button></div></section>
 ${d?`<section class="card spaced"><div class="card-heading"><div><h2>${esc(tasks[d.task])} · 產生紀錄</h2><p>${esc(d.runId)} · ${esc(d.runStatus)} · 基準 ${esc(d.baselineVersionId)}<br>有候選本文 ${d.records.filter(r=>r.instruction.text!==null).length} 筆／生成嘗試 ${d.records.length} 筆；不同新本文 ${d.records.filter(r=>r.status==='generated'&&r.novelty==='new').length} 個 · 重複 ${d.records.filter(r=>r.status==='generated'&&r.novelty==='duplicate').length} 筆 · 核准版本 ${d.approvedVersions.length} 個。</p></div><a class="button secondary" href="/api/v1/debug/support?runId=${encodeURIComponent(d.runId)}">下載此 Run 診斷包</a></div>
 ${d.warnings.map(w=>`<p class="small-notice">${esc(w)}</p>`).join('')}<p class="small-notice">紀錄不自動刪除。本文中的已知憑證格式會遮蔽；hash 保留原始識別。舊 Run 的條件依保存證據重建，未記錄的時間或原因維持未知。</p><details><summary>基準 Skill 與凍結條件</summary>${code(d.baseline.text)}${code(JSON.stringify(d.conditions,null,2))}</details>
 ${d.records.map(r=>`<details class="skill-step"><summary>${esc(r.id)} · ${esc(r.status)} · ${r.novelty==='duplicate'?`重複本文（${esc(r.duplicateOf)}）`:r.novelty==='new'?'本輪首次出現':r.changed===true?'本文有修改':r.changed===false?'本文未修改':'本文未確認'} · ${r.matchesSelection===true?'本文符合選定內容':r.matchesSelection===false?'未選用':'尚無選定結果'}</summary><p>來源：${r.origin==='recorded'?'產生時紀錄':r.origin==='recovered-response'?'從已保存回覆取回本文・尚未確認有效':'由既有證據重建'} · 開始 ${esc(time(r.startedAt))} · 結束 ${esc(time(r.finishedAt))}<br>Skill hash：<code>${esc(r.instruction.hash??r.instruction.bodyHash??'未知')}</code><br>Parent hash：<code>${esc(r.parent.hash??r.parent.bodyHash??'未知')}</code>${r.errorType?`<br>錯誤類型：${esc(r.errorType)}`:''}${r.validationScore!==null?`<br>搜尋驗證分數：${esc(r.validationScore)}`:''}</p><h3>產生條件</h3>${code(JSON.stringify(r.conditions,null,2))}<h3>對應訓練紀錄</h3>${code(JSON.stringify(r.trainingRefs,null,2))}<div class="diff"><div><h3>Parent Skill</h3>${code(r.parent.text)}</div><div><h3>產生的 Skill</h3>${code(r.instruction.text)}</div></div><h3>版本差異</h3>${code(r.patch||'無已確認的本文差異')}${r.auditMismatch?'<p class="error-banner">來源紀錄不一致，已優先顯示原提案。</p>':''}</details>`).join('')||'<p class="body-copy">沒有保存的提案；這不表示所有訓練題均已測過。</p>'}
 ${d.outcome?`<details><summary>已保存的評測結果（未重新驗證）</summary>${code(JSON.stringify(d.outcome,null,2))}</details>`:''}<details><summary>搜尋略過與停止條件</summary>${code(d.searchAudit?JSON.stringify(d.searchAudit,null,2):'此 Run 未保存搜尋事件；無法補造原因。')}</details><h3>已核准版本</h3>${code(JSON.stringify(d.approvedVersions,null,2))}</section>`:''}</div>`;
}
export function skillArchiveView(state){return `<div class="page-heading"><div><h1>Skill 產生紀錄</h1><p>查詢每個候選、產生條件、Parent、差異與核准版本。讀取紀錄不呼叫模型。</p></div></div><section class="card"><form id="skill-archive-form"><label>Run ID（留空查詢列表）<input name="runId" placeholder="RUN-…"></label><label>類型<select name="task"><option value="">所有 Skill</option>${Object.entries(tasks).map(([k,v])=>`<option value="${k}" ${state.task===k?'selected':''}>${v}</option>`).join('')}</select></label><button class="button primary" type="submit" ${state.busy?'disabled':''}>查詢</button></form></section>${skillArchiveResults(state)}`;}
