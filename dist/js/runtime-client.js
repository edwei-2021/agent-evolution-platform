// Live telemetry is ephemeral and separate from browser-local demo/configuration data.
export const LIVE_STATUSES={queued:'等待執行',running:'執行中',completed:'已完成',failed:'失敗',cancelled:'已取消',skipped:'未執行',interrupted:'執行中斷'};
const validTime=v=>typeof v==='string'&&Number.isFinite(Date.parse(v));
const validSkill=v=>v&&v.name==='normalize-support-title'&&typeof v.description==='string'&&v.description.length<500&&typeof v.body==='string'&&v.body.length<3000&&/^[a-f0-9]{64}$/.test(v.hash)&&v.policy&&Object.keys(v.policy).length===4&&['unicode_nfkc','casefold','trim','collapse_whitespace'].every(k=>typeof v.policy[k]==='boolean');
const validMetric=v=>v&&Number.isInteger(v.passed)&&Number.isInteger(v.total)&&v.total>0&&v.total<=50&&v.passed>=0&&v.passed<=v.total&&v.score===v.passed/v.total&&Number.isInteger(v.loss)&&v.loss>=0;
export function validateSkills(value){
  if(!value||value.schemaVersion!==1||value.engine!=='local-rule-search-v1'||!Number.isInteger(value.revision)||value.revision<1||!Array.isArray(value.versions)||!value.versions.length||value.versions.length>100||!Array.isArray(value.actions)||value.actions.length>20||!Array.isArray(value.runs)||value.runs.length>10)throw Error('技能工作台資料格式不正確');
  const ids=new Set();
  for(const v of value.versions){if(!v||typeof v.id!=='string'||!/^SKV-[A-Za-z0-9-]+$/.test(v.id)||ids.has(v.id)||typeof v.label!=='string'||!/^S\d+$/.test(v.label)||!validTime(v.createdAt)||!validSkill(v.skill))throw Error('技能版本資料格式不正確');ids.add(v.id);}
  if(!ids.has(value.activeVersionId)||!value.active||value.active.id!==value.activeVersionId||!validSkill(value.active.skill)||value.active.skill.hash!==value.versions.find(v=>v.id===value.activeVersionId).skill.hash)throw Error('使用中的技能版本不一致');
  if(value.runs.some(r=>!r||!/^RUN-[A-Za-z0-9-]+$/.test(r.id)||!Object.hasOwn(LIVE_STATUSES,r.status)||!validTime(r.createdAt)))throw Error('技能實驗清單格式不正確');
  if(value.latestRun!==null)validateSkillRun(value.latestRun);
  return value;
}
export function validateSkillRun(run){
  validateRuntime({schemaVersion:1,mode:'native-tools',serviceId:'validation',serverTime:new Date().toISOString(),runs:[],latestRun:run});
  if(run.task!=='skill-evolution'||!run.skillConfig||!validSkill(run.skillConfig.baseline?.skill)||!/^SKV-[A-Za-z0-9-]+$/.test(run.skillConfig.baseline?.id)||!/^S\d+$/.test(run.skillConfig.baseline?.label)||!run.skillConfig.provenance||typeof run.skillConfig.provenance.datasetRevision!=='string'||!/^[a-f0-9]{64}$/.test(run.skillConfig.provenance.datasetHash)||!/^[a-f0-9]{64}$/.test(run.skillConfig.provenance.evaluatorHash)||!Number.isInteger(run.skillConfig.maxCandidates)||run.skillConfig.maxCandidates<1||run.skillConfig.maxCandidates>4)throw Error('技能實驗設定不正確');
  const p=run.skillProgress;
  if(p){
    if(p.engine!=='local-rule-search-v1'||!Array.isArray(p.candidates)||p.candidates.length>5||p.candidates.some((c,i)=>c.id!==`C${i}`||!validSkill(c.skill)||!validMetric(c.training)||(c.validation&&!validMetric(c.validation)))||!p.evaluations||['training','validation','heldout','verification'].some(k=>!Number.isInteger(p.evaluations[k])||p.evaluations[k]<0||p.evaluations[k]>1000)||!['queued','coordinator','worker','evaluator','reflector','reviewer'].includes(p.phase))throw Error('技能搜尋進度不正確');
    if(p.trainingFailures&&(!Array.isArray(p.trainingFailures)||p.trainingFailures.length>8||p.trainingFailures.some(r=>!r||['taskId','input','output','expected'].some(k=>typeof r[k]!=='string'||r[k].length>2000))))throw Error('技能訓練紀錄不正確');
  }
  const result=run.skillResult;
  if(result&&(typeof result.eligible!=='boolean'||!['ready-for-human-review','keep-baseline'].includes(result.decision)||!validSkill(result.selectedSkill)||!validMetric(result.selectedValidation)||!validMetric(result.heldout?.baseline)||!validMetric(result.heldout?.selected)))throw Error('技能檢閱證據不正確');
  return run;
}
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
    if(r.events.some(e=>!validTime(e.at)||typeof e.text!=='string'||e.text.length>2000)||r.artifacts.some(name=>typeof name!=='string'||!/^[-A-Za-z0-9_]+\.(json|log|md)$/.test(name)))throw Error('執行紀錄格式不正確');
  }
  if(data.skills!==undefined)validateSkills(data.skills);
  return data;
}
export function telemetryFor(runtime,id){return runtime?.data?.latestRun?.agents.find(a=>a.id===id)||null;}
export function telemetryLabel(runtime,id){
  const agent=telemetryFor(runtime,id);
  return agent?(runtime.error?'狀態過期':LIVE_STATUSES[agent.status]):'尚無執行紀錄';
}
export class RuntimeClient{
  // Native browser fetch requires the global receiver, not this RuntimeClient.
  constructor({fetcher=globalThis.fetch.bind(globalThis),onUpdate=()=>{},interval=2000}={}){this.fetcher=fetcher;this.onUpdate=onUpdate;this.interval=interval;this.data=null;this.capabilities=null;this.error=null;this.lastSuccess=null;this.lastAttempt=null;this.pollCount=0;this.busy=false;this.enabled=false;this.timer=null;this.pendingRequestId=null;this.pendingSkillSubmission=null;this.selectedSkillRun=null;this.skillLimit=4;this.actionBusy=false;}
  snapshot(){return {data:this.data,capabilities:this.capabilities,error:this.error,lastSuccess:this.lastSuccess,lastAttempt:this.lastAttempt,pollCount:this.pollCount,busy:this.busy,enabled:this.enabled,interval:this.interval,selectedSkillRun:this.selectedSkillRun,skillLimit:this.skillLimit,actionBusy:this.actionBusy,skillTrial:this.skillTrial,trialInput:this.trialInput??'  Ｓｅｒｖｉｃｅ   Down  '};}
  async request(path,{method='GET',body}={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    try{
      const response=await this.fetcher(path,{method,cache:'no-store',credentials:'same-origin',signal:controller.signal,headers:method==='POST'?{'Content-Type':'application/json','X-Lab-Token':this.capabilities?.csrfToken||''}:{},...(body?{body:JSON.stringify(body)}:{})});
      let data;try{data=await response.json();}catch{throw Error('此網址沒有本機執行 API，請使用 WSL 的 localhost 介面');}
      if(!response.ok){const error=Error(typeof data.error==='string'?data.error:`執行服務回應 HTTP ${response.status}`);error.status=response.status;throw error;}
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
      if(this.data?.serviceId&&this.data.serviceId!==data.serviceId)this.selectedSkillRun=null;
      if(this.selectedSkillRun){
        if(this.selectedSkillRun.id===data.skills?.latestRun?.id)this.selectedSkillRun=data.skills.latestRun;
        else if(['queued','running'].includes(this.selectedSkillRun.status))this.selectedSkillRun=null;
      }
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
  async skillMutation(operation){
    if(this.actionBusy)throw Error('技能操作正在處理，請稍候');
    this.actionBusy=true;this.onUpdate(this.snapshot());
    try{
      if(!this.capabilities||this.error)await this.refresh();
      if(!this.capabilities||this.error||!this.data?.skills)throw Error('技能服務尚未連線，請更新並啟動 WSL 本機服務');
      await operation();
      await this.refresh();
    }catch(error){await this.refresh();throw error;}
    finally{this.actionBusy=false;this.onUpdate(this.snapshot());}
  }
  async startSkill(registry){
    return this.skillMutation(async()=>{
      this.pendingSkillSubmission ||= {registry:structuredClone(registry),requestId:crypto.randomUUID(),maxCandidates:this.skillLimit,expectedRevision:this.data.skills.revision};
      try{await this.request('/api/v1/skills/runs',{method:'POST',body:this.pendingSkillSubmission});}
      catch(error){if(error.status>=400&&error.status<500)this.pendingSkillSubmission=null;throw error;}
      this.pendingSkillSubmission=null;this.selectedSkillRun=null;
    });
  }
  async approveSkill(id){return this.skillMutation(()=>this.request(`/api/v1/skills/runs/${encodeURIComponent(id)}/approve`,{method:'POST',body:{expectedRevision:this.data.skills.revision}}));}
  async activateSkill(id){return this.skillMutation(()=>this.request(`/api/v1/skills/versions/${encodeURIComponent(id)}/activate`,{method:'POST',body:{expectedRevision:this.data.skills.revision}}));}
  async trySkill(text){
    this.trialInput=text;
    return this.skillMutation(async()=>{
      const result=await this.request('/api/v1/skills/execute',{method:'POST',body:{text,expectedRevision:this.data.skills.revision}});
      if(!result||typeof result.input!=='string'||typeof result.output!=='string'||result.input.length>500||result.output.length>2000||!/^SKV-[A-Za-z0-9-]+$/.test(result.versionId)||!/^[a-f0-9]{64}$/.test(result.skillHash))throw Error('技能試跑回應不正確');
      this.skillTrial=result;
    });
  }
  async selectSkillRun(id){
    this.selectedSkillRun=id?validateSkillRun(await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}`)):null;
    this.onUpdate(this.snapshot());
  }
}
