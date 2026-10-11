// Reads local saved settings only. Ollama HTTP requests require an explicit click.
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function ollamaView(state){
 const {data,error,busy,prompt}=state;
 if(!data)return `<section class="card spaced"><div class="card-heading"><h2>Windows Ollama · 11435</h2></div><p class="body-copy">${esc(error||'讀取本機設定中…')}。請使用 WSL 的 localhost GUI。</p><div class="card-actions"><button class="button secondary" data-ollama="reload" ${busy?'disabled':''}>讀取設定</button></div></section>`;
 const c=data.config,e=data.historicalEvidence,r=data.latest;
 const current=r?.revision===data.revision&&r.endpoint===data.nativeBaseUrl;
 const ids=current&&r.modelIds?r.modelIds:e.modelIds;
 const disabled=busy?'disabled':'';
 const field=(name,label,type='text',extra='')=>`<label>${label}<input name="${name}" type="${type}" value="${esc(c[name])}" ${extra} ${disabled}></label>`;
 return `<section class="card spaced"><div class="card-heading"><div><h2>Windows Ollama 連線設定</h2><p>設定存於 WSL 專案；讀取設定與啟動 GUI 不會呼叫 Windows API。</p></div><span class="soft-tag">OPENAI COMPATIBLE</span></div>
 <div class="small-notice"><strong>已提供的實機證據：API 連通成功，推論尚未測試。</strong><br>${esc(e.observedAt)} · Ollama ${esc(e.serverVersion)} · ${e.modelIds.length} 個模型 · ${esc(e.openaiBaseUrl)}。這是歷史紀錄，尚未代表目前模型可推論。</div>
 ${error?`<div class="error-banner" role="alert">${esc(error)}</div>`:''}
 <form id="ollama-settings-form" class="ollama-form"><div class="two-col">
 ${field('host','Windows IPv4（留空：自動偵測 WSL NAT gateway）')}
 ${field('port','Windows Ollama port','number','min="1" max="65535" required')}
 ${field('model','模型完整 ID（歷史清單可供參考）','text','list="ollama-model-ids" maxlength="200"')}
 ${field('metadataTimeout','Metadata timeout（秒）','number','min="1" max="120" required')}
 ${field('inferenceTimeout','Inference timeout（秒）','number','min="1" max="3600" required')}
 ${field('maxTokens','最大輸出 tokens','number','min="1" max="8192" required')}
 </div><datalist id="ollama-model-ids">${ids.map(id=>`<option value="${esc(id)}"></option>`).join('')}</datalist>
 <p class="body-copy">目前解析的 API：<code>${esc(data.openaiBaseUrl||data.discoveryError)}</code><br>Proxy：所有橋接請求皆略過。GUI port 預設 8765，與 Ollama port 分開設定。</p>
 <div class="actions card-actions"><button class="button primary" ${disabled}>儲存設定</button><button type="button" class="button secondary" data-ollama="reload" ${disabled}>重新讀取設定</button><button type="button" class="button secondary" data-ollama="metadata" ${disabled}>手動更新模型清單</button></div></form>
 <div class="small-notice">更新模型清單與試跑使用已儲存設定。名稱含 cloud 的模型可能使用遠端服務；請自行選擇已安裝模型。技能演化目前仍使用規則引擎，尚未串接此模型。</div>
 <form id="ollama-chat-form" class="ollama-form"><label>單次模型試跑（按下才送出）<textarea name="prompt" required maxlength="4000" rows="3" ${disabled}>${esc(prompt)}</textarea></label><div class="actions card-actions"><button class="button secondary" ${busy||!c.model?'disabled':''}>送出一次推論</button><span>${busy?'操作處理中；請勿重複送出':'不會自動測試或重試'}</span></div></form>
 ${r?`<div class="small-notice">最近請求：${esc(r.status)} · ${esc(r.finishedAt)} · ${r.elapsedMs} ms · ${current?'目前已儲存設定':'先前設定，請勿視為目前連線狀態'}<br><code>${esc(r.reportPath)}</code></div><pre class="ollama-output">${esc(r.error||r.content||JSON.stringify(r.modelIds,null,2))}</pre>`:''}</section>`;
}

export class OllamaUI{
 constructor({fetcher=globalThis.fetch.bind(globalThis),token=()=>'',onUpdate=()=>{}}={}){
  this.fetcher=fetcher;this.token=token;this.onUpdate=onUpdate;this.data=null;this.error=null;this.busy=false;this.prompt='Reply with the word OK.';
 }
 snapshot(){return {data:this.data,error:this.error,busy:this.busy,prompt:this.prompt};}
 view(){return ollamaView(this.snapshot());}
 async request(path,body,timeout=15000){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{
   const token=body?await this.token():null;
   const response=await this.fetcher(path,{method:body?'POST':'GET',cache:'no-store',credentials:'same-origin',signal:controller.signal,headers:body?{'Content-Type':'application/json','X-Lab-Token':token||''}:{},...(body?{body:JSON.stringify(body)}:{})});
   let value;try{value=await response.json();}catch{throw Error('此網址沒有本機 LLM API，請使用 WSL 的 localhost GUI');}
   if(!response.ok)throw Error(value.error||`LLM API HTTP ${response.status}`);
   return value;
  }finally{clearTimeout(timer);}
 }
 async operate(action,config){
  if(this.busy)throw Error('Ollama 操作正在處理');
  this.busy=true;this.error=null;this.onUpdate();
  try{
   if(action==='save')this.data=await this.request('/api/v1/llm/ollama/settings',{config,expectedRevision:this.data.revision});
   else if(action==='reload')this.data=await this.request('/api/v1/llm/ollama');
   else{
    if(!['metadata','chat'].includes(action)||!this.data)throw Error('請先讀取 Ollama 設定');
    const timeout=action==='chat'?(this.data.config.inferenceTimeout+15)*1000:(this.data.config.metadataTimeout*3+15)*1000;
    const result=await this.request(`/api/v1/llm/ollama/${action}`,{expectedRevision:this.data.revision,...(action==='chat'?{prompt:this.prompt}:{})},timeout);
    this.data=await this.request('/api/v1/llm/ollama');
    if(result.status==='FAIL')throw Error(result.error||'Ollama 請求失敗');
   }
  }catch(error){this.error=error.name==='AbortError'?'等待逾時；後端請求可能仍在執行，請重新讀取設定查看紀錄。系統不會自動重試。':error.message;throw error;}
  finally{this.busy=false;this.onUpdate();}
 }
}
