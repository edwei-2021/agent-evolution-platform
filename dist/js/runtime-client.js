// Live telemetry is ephemeral and separate from browser-local demo/configuration data.
export const LIVE_STATUSES={queued:'等待執行',running:'執行中',completed:'已完成',failed:'失敗',cancelled:'已取消',skipped:'未執行',interrupted:'執行中斷'};
const validTime=v=>typeof v==='string'&&Number.isFinite(Date.parse(v));
export function validateRuntime(data){
  if(!data||data.schemaVersion!==1||data.mode!=='native-tools'||typeof data.serviceId!=='string'||!validTime(data.serverTime)||!Array.isArray(data.runs)||data.runs.length>10)throw Error('執行服務資料格式不正確');
  if(data.runs.some(r=>!r||typeof r.id!=='string'||!/^RUN-[A-Za-z0-9-]+$/.test(r.id)||!Object.hasOwn(LIVE_STATUSES,r.status)||!validTime(r.createdAt)))throw Error('流程清單格式不正確');
  const r=data.latestRun;
  if(r!==null){
    if(!r||typeof r.id!=='string'||!/^RUN-[A-Za-z0-9-]+$/.test(r.id)||!Object.hasOwn(LIVE_STATUSES,r.status)||!validTime(r.createdAt)||!validTime(r.updatedAt)||r.mode!=='native-tools'||!Array.isArray(r.agents)||r.agents.length!==5||!Array.isArray(r.events)||r.events.length>200||!Array.isArray(r.artifacts)||r.artifacts.length>50)throw Error('工作執行資料格式不正確');
    const ids=new Set();
    for(const a of r.agents){
      if(!a||typeof a.id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(a.id)||ids.has(a.id)||typeof a.name!=='string'||a.name.length>80||!Object.hasOwn(LIVE_STATUSES,a.status)||!validTime(a.updatedAt)||!(a.pid===null||Number.isInteger(a.pid)&&a.pid>0)||!(a.processAlive===null||typeof a.processAlive==='boolean')||typeof a.logTail!=='string'||a.logTail.length>20000)throw Error('代理人執行資料格式不正確');
      ids.add(a.id);
    }
    if(r.events.some(e=>!validTime(e.at)||typeof e.text!=='string'||e.text.length>2000)||r.artifacts.some(name=>typeof name!=='string'||!/^[-A-Za-z0-9_]+\.(json|log)$/.test(name)))throw Error('執行紀錄格式不正確');
  }
  return data;
}
export function telemetryFor(runtime,id){return runtime?.data?.latestRun?.agents.find(a=>a.id===id)||null;}
export function telemetryLabel(runtime,id){
  const agent=telemetryFor(runtime,id);
  return agent?(runtime.error?'狀態過期':LIVE_STATUSES[agent.status]):'尚無執行紀錄';
}
export class RuntimeClient{
  // Native browser fetch requires the global receiver, not this RuntimeClient.
  constructor({fetcher=globalThis.fetch.bind(globalThis),onUpdate=()=>{},interval=2000}={}){this.fetcher=fetcher;this.onUpdate=onUpdate;this.interval=interval;this.data=null;this.capabilities=null;this.error=null;this.lastSuccess=null;this.lastAttempt=null;this.pollCount=0;this.busy=false;this.enabled=false;this.timer=null;this.pendingRequestId=null;}
  snapshot(){return {data:this.data,capabilities:this.capabilities,error:this.error,lastSuccess:this.lastSuccess,lastAttempt:this.lastAttempt,pollCount:this.pollCount,busy:this.busy,enabled:this.enabled,interval:this.interval};}
  async request(path,{method='GET',body}={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    try{
      const response=await this.fetcher(path,{method,cache:'no-store',credentials:'same-origin',signal:controller.signal,headers:method==='POST'?{'Content-Type':'application/json','X-Lab-Token':this.capabilities?.csrfToken||''}:{},...(body?{body:JSON.stringify(body)}:{})});
      let data;try{data=await response.json();}catch{throw Error('此網址沒有本機執行 API，請使用 WSL 的 localhost 介面');}
      if(!response.ok)throw Error(typeof data.error==='string'?data.error:`執行服務回應 HTTP ${response.status}`);
      return data;
    }finally{clearTimeout(timer);}
  }
  async refresh(){
    if(this.busy)return false;
    this.busy=true;this.lastAttempt=new Date().toISOString();this.pollCount++;
    try{
      if(!this.capabilities){
        const c=await this.request('/api/v1/runtime/capabilities');
        if(c.mode!=='native-tools'||c.schemaVersion!==1||typeof c.csrfToken!=='string'||c.csrfToken.length<20||typeof c.serviceId!=='string')throw Error('執行服務能力格式不正確');
        this.capabilities=c;
      }
      const data=validateRuntime(await this.request('/api/v1/runtime'));
      if(data.serviceId!==this.capabilities.serviceId){this.capabilities=null;throw Error('服務已重新啟動；下次 polling 會重新取得連線資訊');}
      this.data=data;this.error=null;this.lastSuccess=new Date().toISOString();
      if(this.pendingRequestId===data.latestRun?.requestId)this.pendingRequestId=null;
      return true;
    }catch(error){this.error=error.name==='AbortError'?'執行服務逾時；保留最後快照並繼續重試':error.message;this.capabilities=null;return false;}
    finally{this.busy=false;this.onUpdate(this.snapshot());}
  }
  schedule(){clearTimeout(this.timer);if(this.enabled)this.timer=setTimeout(async()=>{await this.refresh();this.schedule();},this.interval);}
  async start(){this.enabled=true;await this.refresh();this.schedule();}
  stop(){this.enabled=false;clearTimeout(this.timer);this.onUpdate(this.snapshot());}
  setInterval(ms){if(![1000,2000,5000,10000].includes(Number(ms)))throw Error('Polling 間隔不受支援');this.interval=Number(ms);this.schedule();this.onUpdate(this.snapshot());}
  async run(registry){
    if(!this.capabilities||this.error){await this.refresh();if(!this.capabilities||this.error)throw Error('本機執行服務尚未連線，請先啟動 WSL 服務');}
    this.pendingRequestId ||= crypto.randomUUID();
    await this.request('/api/v1/runtime/runs',{method:'POST',body:{registry,requestId:this.pendingRequestId}});
    this.pendingRequestId=null;await this.refresh();
  }
  async cancel(id){await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}/cancel`,{method:'POST',body:{}});await this.refresh();}
}
