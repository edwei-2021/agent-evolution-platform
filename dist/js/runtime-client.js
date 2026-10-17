// Live telemetry is ephemeral and separate from browser-local demo/configuration data.
import {validateChanges} from './changes-client.js';
import {GEPA_PRESETS} from './gepa-plan.js';
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
    if(r.events.some(e=>!validTime(e.at)||typeof e.text!=='string'||e.text.length>2000)||r.artifacts.some(name=>typeof name!=='string'||!/^[-A-Za-z0-9_]+\.(json|log|md|py|patch)$/.test(name)))throw Error('執行紀錄格式不正確');
  }
  if(data.skills!==undefined)validateSkills(data.skills);
  if(data.provider!==undefined){
    const p=data.provider,w=p?.warmup;
    if(!p||!Number.isInteger(p.revision)||typeof p.config?.model!=='string'||!Number.isInteger(p.config.inferenceTimeout)||typeof p.busy!=='boolean')throw Error('模型服務狀態不正確');
    if(w&&(!/^WARM-[A-Za-z0-9-]+$/.test(w.id)||!['RUNNING','PRELOAD_PASS','FAIL','CANCELLED','INTERRUPTED'].includes(w.status)||!validTime(w.startedAt)||w.finishedAt&&!validTime(w.finishedAt)||!Number.isFinite(w.elapsedSeconds)||w.elapsedSeconds<0||!Number.isInteger(w.timeoutSeconds)||typeof w.config?.model!=='string'))throw Error('模型暖機狀態不正確');
  }
  if(data.llm!==undefined)validateLlmWorkspace(data.llm);
  if(data.repair!==undefined)validateRepairWorkspace(data.repair);
  if(data.gepa!==undefined)validateGepaWorkspace(data.gepa);
  return data;
}
const validPrompt=v=>v&&v.name==='normalize-support-title'&&typeof v.description==='string'&&typeof v.body==='string'&&v.body.length>0&&v.body.length<=3000&&/^[a-f0-9]{64}$/.test(v.hash);
export function validateLlmRun(run){
  validateRuntime({schemaVersion:1,mode:'native-tools',serviceId:'validation',serverTime:new Date().toISOString(),runs:[],latestRun:run});
  if(run.task!=='llm-evolution'||!run.llmConfig||!validPrompt(run.llmConfig.baseline?.skill)||!['smoke','full'].includes(run.llmConfig.profile)||![15,101].includes(run.llmConfig.callBudget)||typeof run.llmConfig.provider?.config?.model!=='string')throw Error('模型技能實驗設定不正確');
  const p=run.llmProgress;
  if(p&&(p.engine!=='ollama-prompt-reflection-v1'||!Number.isInteger(p.calls)||p.calls<0||p.calls>run.llmConfig.callBudget||!Array.isArray(p.candidates)||p.candidates.length>2||p.candidates.some((c,i)=>c.id!==`C${i}`||!validPrompt(c.skill)||(c.training&&!validMetric(c.training))||(c.validation&&!validMetric(c.validation)))||!Array.isArray(p.trainingFailures)||p.trainingFailures.length>8))throw Error('模型技能進度不正確');
  if(p){
    for(const field of ['completedCalls','failedCalls'])if(p[field]!==undefined&&(!Number.isInteger(p[field])||p[field]<0||p[field]>p.calls))throw Error('模型呼叫計數不正確');
    if((p.completedCalls||0)+(p.failedCalls||0)>p.calls)throw Error('模型呼叫計數不一致');
    const c=p.lastCall;
    if(c){
      if(!Number.isInteger(c.id)||c.id<1||c.id>p.calls||!['running','completed','failed','cancelled'].includes(c.status))throw Error('模型呼叫狀態不正確');
      for(const field of ['startedAt','finishedAt','deadlineEpoch','lastChunkAt','timeoutSeconds','chunks','outputChars','reasoningChars'])if(c[field]!==undefined&&(!Number.isFinite(c[field])||c[field]<0))throw Error('模型回應進度不正確');
    }
  }
  if(run.llmResult&&(typeof run.llmResult.eligible!=='boolean'||!validPrompt(run.llmResult.selectedSkill)||!validMetric(run.llmResult.selectedValidation)||!validMetric(run.llmResult.heldout?.baseline)||!validMetric(run.llmResult.heldout?.selected)))throw Error('模型技能證據不正確');
  return run;
}
export function validateLlmWorkspace(w){
 if(!w||w.schemaVersion!==1||w.engine!=='ollama-prompt-reflection-v1'||!Number.isInteger(w.revision)||w.revision<1||!Array.isArray(w.versions)||!w.versions.length||w.versions.length>100||w.versions.some(v=>!/^LSV-[A-Za-z0-9-]+$/.test(v.id)||!validPrompt(v.skill))||new Set(w.versions.map(v=>v.id)).size!==w.versions.length||!w.versions.some(v=>v.id===w.activeVersionId)||w.active?.id!==w.activeVersionId||!validPrompt(w.active?.skill)||!Array.isArray(w.runs)||w.runs.length>10)throw Error('模型技能工作台格式不正確');
 if(w.latestRun)validateLlmRun(w.latestRun);
 return w;
}
export function validateRepairRun(run){
 validateRuntime({schemaVersion:1,mode:'native-tools',serviceId:'validation',serverTime:new Date().toISOString(),runs:[],latestRun:run});
 const c=run.repairConfig,p=run.repairProgress,r=run.repairResult;
 if(run.task!=='nanobot-repair'||c?.engine!=='nanobot-python-repair-v1'||c.sdk?.version!=='0.3.5'||c.skill?.name!=='python-fix-and-verify'||!Number.isInteger(c.callBudget)||c.callBudget<2||c.callBudget>12||typeof c.provider?.config?.model!=='string')throw Error('Python 修復設定不正確');
 if(p&&(p.engine!=='nanobot-python-repair-v1'||!Number.isInteger(p.calls)||p.calls<0||p.calls>c.callBudget||!Number.isInteger(p.completedCalls)||p.completedCalls<0||p.completedCalls>p.calls||!Number.isInteger(p.toolCalls)||p.toolCalls<0||p.toolCalls>24))throw Error('Python 修復進度不正確');
 if(p?.lastCall){const t=p.lastCall;if(!Number.isInteger(t.id)||t.id<1||t.id>p.calls||!['running','completed','failed','cancelled'].includes(t.status))throw Error('修復模型呼叫狀態不正確');for(const name of ['startedAt','finishedAt','lastChunkAt','deadlineEpoch','timeoutSeconds','chunks','outputChars','reasoningChars','toolArgumentChars'])if(t[name]!==undefined&&(!Number.isFinite(t[name])||t[name]<0))throw Error('修復模型回應進度不正確');}
 if(r){if(typeof r.repairPassed!=='boolean'||r.sdkVersion!=='0.3.5'||!/^[a-f0-9]{64}$/.test(r.evidenceHash))throw Error('Python 修復證據不正確');for(const group of [r.baseline,r.candidate])for(const split of ['visible','hidden']){const m=group?.[split];if(!m||m.total!==6||!Number.isInteger(m.passed)||m.passed<0||m.passed>m.total)throw Error('Python 修復評測不正確');}if(r.repairPassed!==['visible','hidden'].every(split=>r.candidate[split].passed===6))throw Error('修復結果與測試計數不一致');}
 return run;
}
export function validateRepairWorkspace(w){
 if(w?.engine!=='nanobot-python-repair-v1'||typeof w.sdk?.available!=='boolean'||!Array.isArray(w.runs)||w.runs.length>10)throw Error('Python 修復工作台不正確');
 if(w.latestRun)validateRepairRun(w.latestRun);return w;
}
const validGepaSkill=s=>s?.name==='python-fix-and-verify'&&typeof s.description==='string'&&typeof s.body==='string'&&s.body.length>0&&s.body.length<=8000&&/^[a-f0-9]{64}$/.test(s.hash);
export function validateGepaRun(run){
 validateRuntime({schemaVersion:1,mode:'native-tools',serviceId:'validation',serverTime:new Date().toISOString(),runs:[],latestRun:run});
 const c=run.gepaConfig,p=run.gepaProgress,r=run.gepaResult;
 if(run.task!=='gepa-evolution'||c?.engine!=='gepa-nanobot-repair-v1'||c.sdk?.version!=='0.3.5'||c.optimizer?.version!=='0.1.4'||!validGepaSkill(c.baseline?.skill)||!['smoke','full','bank'].includes(c.profile)||!Number.isInteger(c.callBudget)||c.callBudget<1||c.callBudget>1688||!Number.isInteger(c.metricBudget)||c.metricBudget<6||c.metricBudget>80||typeof c.provider?.config?.model!=='string')throw Error('GEPA 設定不正確');
 if(c.profile==='bank'){const n=c.counts;if(!n||['train','validation','heldout'].some(k=>!Number.isInteger(n[k])||n[k]<2||n[k]>(k==='train'?30:20))||n.validation+n.heldout>30||n.train+n.validation+n.heldout>50||c.datasetSnapshot?.revision!==c.bankRevision||c.datasetSnapshot?.version!=='python-challenges-v1')throw Error('題庫凍結資料不正確');}
 else for(const [key,count] of Object.entries(c.profile==='smoke'?{train:4,validation:2,heldout:4}:{train:20,validation:10,heldout:20}))if(c.counts?.[key]!==count)throw Error('GEPA 資料分割不正確');
 if(p){
  if(p.engine!=='gepa-nanobot-repair-v1')throw Error('GEPA 進度不正確');
  for(const [key,max] of [['calls',c.callBudget],['completedCalls',p.calls],['failedCalls',p.calls],['metricEvaluations',c.metricBudget],['proposals',c.proposalBudget],['rollouts',c.metricBudget+2*(c.counts.validation+c.counts.heldout)]])if(!Number.isInteger(p[key])||p[key]<0||p[key]>max)throw Error('GEPA 計數不正確');
  if(p.lastCall){const t=p.lastCall;if(!Number.isInteger(t.id)||t.id<1||t.id>p.calls||!['running','completed','failed','cancelled'].includes(t.status))throw Error('GEPA 呼叫狀態不正確');for(const key of ['startedAt','finishedAt','deadlineEpoch','timeoutSeconds','chunks','outputChars','reasoningChars','toolArgumentChars'])if(t[key]!==undefined&&(!Number.isFinite(t[key])||t[key]<0))throw Error('GEPA 模型進度不正確');}
  if(p.selectedSkill&&!validGepaSkill(p.selectedSkill))throw Error('GEPA 候選格式不正確');
 }
 if(r){
  if(r.engine!=='gepa-nanobot-repair-v1'||r.checksPassed!==true||typeof r.eligible!=='boolean'||!validGepaSkill(r.selectedSkill)||!validGepaSkill(r.baselineSkill)||!/^[a-f0-9]{64}$/.test(r.evidenceHash))throw Error('GEPA 證據不正確');
  for(const label of ['baseline','selected'])for(const split of ['validation','heldout']){const m=r.final?.[label]?.[split];if(!m||m.total!==c.counts[split]||!Number.isInteger(m.passed)||m.passed<0||m.passed>m.total)throw Error('GEPA 評測格式不正確');}
  if(r.breakdown){for(const dim of ['difficulty','topic']){const table=r.breakdown[dim];if(!table||typeof table!=='object'||Array.isArray(table)||Object.keys(table).length>30)throw Error('GEPA 分項格式不正確');for(const label of ['baseline','selected'])for(const split of ['validation','heldout']){let passed=0,total=0;for(const row of Object.values(table)){const m=row?.[label]?.[split];if(!m||!Number.isInteger(m.total)||m.total<0||m.total>c.counts[split]||!Number.isInteger(m.passed)||m.passed<0||m.passed>m.total)throw Error('GEPA 分項計數不正確');passed+=m.passed;total+=m.total;}if(passed!==r.final[label][split].passed||total!==r.final[label][split].total)throw Error('GEPA 分項與總分不一致');}}}
  const eligible=r.selectedSkill.hash!==r.baselineSkill.hash&&r.final.selected.validation.passed>r.final.baseline.validation.passed&&r.final.selected.heldout.passed>=r.final.baseline.heldout.passed;
  if(r.eligible!==eligible)throw Error('GEPA 核准門檻與證據不一致');
 }
 return run;
}
export function validateGepaWorkspace(w){
 if(w?.schemaVersion!==1||w.engine!=='gepa-nanobot-repair-v1'||!Number.isInteger(w.revision)||w.revision<1||!Array.isArray(w.versions)||!w.versions.length||w.versions.length>100||w.versions.some(v=>!/^GSV-[A-Za-z0-9-]+$/.test(v.id)||!validGepaSkill(v.skill))||new Set(w.versions.map(v=>v.id)).size!==w.versions.length||w.active?.id!==w.activeVersionId||!w.versions.some(v=>v.id===w.activeVersionId)||!validGepaSkill(w.active?.skill)||typeof w.sdk?.available!=='boolean'||typeof w.optimizer?.available!=='boolean'||!Array.isArray(w.runs)||w.runs.length>10)throw Error('GEPA 工作台格式不正確');
 if(w.latestRun)validateGepaRun(w.latestRun);return w;
}
export function telemetryFor(runtime,id){return runtime?.data?.latestRun?.agents.find(a=>a.id===id)||null;}
export function telemetryLabel(runtime,id){
  const agent=telemetryFor(runtime,id);
  return agent?(runtime.error?'狀態過期':LIVE_STATUSES[agent.status]):'尚無執行紀錄';
}
export class RuntimeClient{
  // Native browser fetch requires the global receiver, not this RuntimeClient.
  constructor({fetcher=globalThis.fetch.bind(globalThis),onUpdate=()=>{},interval=2000}={}){this.fetcher=fetcher;this.onUpdate=onUpdate;this.interval=interval;this.data=null;this.capabilities=null;this.error=null;this.lastSuccess=null;this.lastAttempt=null;this.pollCount=0;this.busy=false;this.enabled=false;this.timer=null;this.pendingRequestId=null;this.pendingSkillSubmission=null;this.selectedSkillRun=null;this.skillLimit=4;this.actionBusy=false;this.llmProfile='smoke';this.llmSeconds=900;this.llmCallSeconds=120;this.selectedLlmRun=null;this.pendingLlmSubmission=null;this.pendingRepairSubmission=null;this.selectedRepairRun=null;this.repairSeconds=900;this.repairCallSeconds=120;this.repairBudget=8;this.repairEvidence=null;this.repairEvidenceError=null;this.gepaProfile='smoke';this.gepaMetrics=8;this.gepaProposals=2;this.gepaTaskCalls=8;this.gepaSeconds=1800;this.gepaCallSeconds=120;this.selectedGepaRun=null;this.pendingGepaSubmission=null;}
  snapshot(){return {changes:this.changes,changeBusy:this.changeBusy,changeError:this.changeError,changeRevision:this.changeRevision,data:this.data,capabilities:this.capabilities,error:this.error,lastSuccess:this.lastSuccess,lastAttempt:this.lastAttempt,pollCount:this.pollCount,busy:this.busy,enabled:this.enabled,interval:this.interval,selectedSkillRun:this.selectedSkillRun,skillLimit:this.skillLimit,actionBusy:this.actionBusy,skillTrial:this.skillTrial,trialInput:this.trialInput??'  Ｓｅｒｖｉｃｅ   Down  ',llmProfile:this.llmProfile,llmSeconds:this.llmSeconds,llmCallSeconds:this.llmCallSeconds,selectedLlmRun:this.selectedLlmRun,selectedRepairRun:this.selectedRepairRun,repairSeconds:this.repairSeconds,repairCallSeconds:this.repairCallSeconds,repairBudget:this.repairBudget,repairEvidence:this.repairEvidence,repairEvidenceError:this.repairEvidenceError,gepaProfile:this.gepaProfile,gepaMetrics:this.gepaMetrics,gepaProposals:this.gepaProposals,gepaTaskCalls:this.gepaTaskCalls,gepaSeconds:this.gepaSeconds,gepaCallSeconds:this.gepaCallSeconds,selectedGepaRun:this.selectedGepaRun};}
  async request(path,{method='GET',body,timeoutMs=8000}={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
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
      if(this.data?.serviceId&&this.data.serviceId!==data.serviceId){this.selectedSkillRun=null;this.selectedLlmRun=null;this.selectedRepairRun=null;this.selectedGepaRun=null;this.repairEvidence=null;this.changes=null;this.changeError=null;this.changeGeneration=(this.changeGeneration??0)+1;this.changeBusy=false;this.changeRevision=(this.changeRevision??0)+1;}
      if(this.selectedSkillRun){
        if(this.selectedSkillRun.id===data.skills?.latestRun?.id)this.selectedSkillRun=data.skills.latestRun;
        else if(['queued','running'].includes(this.selectedSkillRun.status))this.selectedSkillRun=null;
      }
      if(this.selectedLlmRun&&this.selectedLlmRun.id===data.llm?.latestRun?.id)this.selectedLlmRun=data.llm.latestRun;
      if(this.pendingLlmSubmission?.requestId===data.latestRun?.requestId)this.pendingLlmSubmission=null;
      if(this.selectedRepairRun&&this.selectedRepairRun.id===data.repair?.latestRun?.id)this.selectedRepairRun=data.repair.latestRun;
      if(this.pendingRepairSubmission?.requestId===data.latestRun?.requestId)this.pendingRepairSubmission=null;
      if(this.selectedGepaRun&&this.selectedGepaRun.id===data.gepa?.latestRun?.id)this.selectedGepaRun=data.gepa.latestRun;
      if(this.pendingGepaSubmission?.requestId===data.latestRun?.requestId)this.pendingGepaSubmission=null;
      this.data=data;this.error=null;this.lastSuccess=new Date().toISOString();
      if(this.pendingRequestId===data.latestRun?.requestId)this.pendingRequestId=null;
      return true;
    }catch(error){this.error=error.name==='AbortError'?'執行服務逾時；保留最後快照並繼續重試':error.message;this.capabilities=null;return false;}
    finally{this.busy=false;this.onUpdate(this.snapshot());}
  }
  async warmModel(){
    if(this.actionBusy)throw Error('操作正在處理');
    this.actionBusy=true;this.onUpdate();
    try{const provider=await this.request('/api/v1/llm/ollama');await this.request('/api/v1/llm/ollama/warmup',{method:'POST',body:{expectedRevision:provider.revision,keepAliveMinutes:15}});await this.refresh();}
    finally{this.actionBusy=false;this.onUpdate();}
  }
  async cancelWarmup(id){await this.request(`/api/v1/llm/ollama/warmup/${encodeURIComponent(id)}/cancel`,{method:'POST',body:{}});await this.refresh();}
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
  async skillMutation(operation,workspace='skills'){
    if(this.actionBusy)throw Error('技能操作正在處理，請稍候');
    this.actionBusy=true;this.onUpdate(this.snapshot());
    try{
      if(!this.capabilities||this.error)await this.refresh();
      if(!this.capabilities||this.error||!this.data?.[workspace])throw Error('技能服務尚未連線，請更新並啟動 WSL 本機服務');
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
  async startLlm(registry){
    return this.skillMutation(async()=>{
      if(!this.data.llm)throw Error('請更新模型技能後端');
      if(!this.pendingLlmSubmission){
        const provider=await this.request('/api/v1/llm/ollama');
        this.pendingLlmSubmission={registry:structuredClone(registry),requestId:crypto.randomUUID(),profile:this.llmProfile,maxSeconds:this.llmSeconds,callTimeoutSeconds:this.llmCallSeconds,expectedRevision:this.data.llm.revision,providerRevision:provider.revision};
      }
      try{await this.request('/api/v1/llm/skills/runs',{method:'POST',body:this.pendingLlmSubmission});}
      catch(error){if(error.status>=400&&error.status<500)this.pendingLlmSubmission=null;throw error;}
      this.pendingLlmSubmission=null;this.selectedLlmRun=null;
    },'llm');
  }
  async approveLlm(id){return this.skillMutation(()=>this.request(`/api/v1/llm/skills/runs/${encodeURIComponent(id)}/approve`,{method:'POST',body:{expectedRevision:this.data.llm.revision}}),'llm');}
  async activateLlm(id){return this.skillMutation(()=>this.request(`/api/v1/llm/skills/versions/${encodeURIComponent(id)}/activate`,{method:'POST',body:{expectedRevision:this.data.llm.revision}}),'llm');}
  async startRepair(registry){
    if(this.actionBusy)throw Error('操作正在處理');
    if(!this.capabilities||this.error||!this.data?.repair?.sdk?.available)throw Error('本機 SDK 尚未可用；請安裝並更新狀態');
    this.actionBusy=true;this.onUpdate();
    try{
      if(!this.pendingRepairSubmission){const provider=await this.request('/api/v1/llm/ollama');this.pendingRepairSubmission={registry:structuredClone(registry),requestId:crypto.randomUUID(),maxSeconds:this.repairSeconds,callTimeoutSeconds:this.repairCallSeconds,callBudget:this.repairBudget,providerRevision:provider.revision};}
      // Submission may revalidate an expired SDK observation: 120s probe + 30s response grace.
      try{await this.request('/api/v1/repair/runs',{method:'POST',body:this.pendingRepairSubmission,timeoutMs:150000});this.pendingRepairSubmission=null;this.selectedRepairRun=null;this.repairEvidence=null;await this.refresh();}
      catch(error){if(error.status&&error.status<500)this.pendingRepairSubmission=null;throw error;}
    }finally{this.actionBusy=false;this.onUpdate();}
  }
  async selectRepairRun(id){this.selectedRepairRun=id?validateRepairRun(await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}`)):null;this.repairEvidence=null;this.repairEvidenceError=null;this.onUpdate();}
  async readRepairEvidence(id){
    this.actionBusy=true;this.repairEvidenceError=null;this.onUpdate();
    try{
      const names=['repair-baseline.py','repair-candidate.py','repair-tools.json','repair-change.patch'];
      const files=await Promise.all(names.map(n=>this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}/artifacts/${n}`)));
      if(files.some(f=>f.truncated))throw Error('證據預覽超限；請在 WSL 檢閱完整檔案');
      const tools=JSON.parse(files[2].content);if(!Array.isArray(tools)||tools.length>24||tools.some(t=>!Number.isInteger(t.id)||t.id<1||t.id>24||!['completed','failed'].includes(t.status)||!['read_solution','write_solution','run_tests'].includes(t.name)))throw Error('工具 trace 不正確');
      this.repairEvidence={runId:id,baseline:files[0].content,candidate:files[1].content,tools,patch:files[3].content};
    }catch(error){this.repairEvidenceError=error.message;throw error;}
    finally{this.actionBusy=false;this.onUpdate();}
  }
  async startGepa(registry){
    return this.skillMutation(async()=>{
      if(!this.data.gepa?.sdk.available||!this.data.gepa?.optimizer.available)throw Error('請安裝 nanobot 與 GEPA');
      if(!this.pendingGepaSubmission){const provider=await this.request('/api/v1/llm/ollama');this.pendingGepaSubmission={registry:structuredClone(registry),requestId:crypto.randomUUID(),profile:this.gepaProfile,maxSeconds:this.gepaSeconds,callTimeoutSeconds:this.gepaCallSeconds,taskCallBudget:this.gepaTaskCalls,metricBudget:this.gepaMetrics,proposalBudget:this.gepaProposals,expectedRevision:this.data.gepa.revision,providerRevision:provider.revision,...(this.gepaProfile==='bank'?{bankRevision:this.data.challenges?.revision}: {})};}
      // Two serial pinned probes (nanobot + GEPA), then response/dispatch grace.
      try{await this.request('/api/v1/gepa/runs',{method:'POST',body:this.pendingGepaSubmission,timeoutMs:270000});}
      catch(error){if(error.status>=400&&error.status<500)this.pendingGepaSubmission=null;throw error;}
      this.pendingGepaSubmission=null;this.selectedGepaRun=null;
    },'gepa');
  }
  setGepaProfile(profile){
    if(!Object.hasOwn(GEPA_PRESETS,profile))throw Error('GEPA 規模不正確');
    this.gepaProfile=profile;const p=GEPA_PRESETS[profile];this.gepaTaskCalls=profile==='bank'?10:8;
    this.gepaMetrics=profile==='bank'?Math.max(p.metrics,2*(this.data?.challenges?.counts.validation??3)+4):p.metrics;this.gepaProposals=p.proposals;this.gepaSeconds=p.seconds;
  }
  async readChanges(id,rollout='',offset=0){
    if(!/^RUN-[A-Za-z0-9-]+$/.test(id)||rollout&&!/^R\d{4}$/.test(rollout)||!Number.isInteger(offset)||offset<0||offset>200)throw Error('修改歷程選擇不正確');
    const generation=(this.changeGeneration??0)+1,service=this.data?.serviceId;
    this.changeGeneration=generation;this.changeBusy=true;this.changeError=null;this.changeRevision=(this.changeRevision??0)+1;this.onUpdate();
    try{
      const query=new URLSearchParams({rollout,offset:String(offset)});
      const data=validateChanges(await this.request(`/api/v1/debug/changes/${encodeURIComponent(id)}?${query}`,{timeoutMs:30000}));
      if(data.runId!==id||rollout&&data.selectedRollout!==rollout||data.offset!==offset)throw Error('歷程與選取的 Run／rollout 不一致');
      if(generation!==this.changeGeneration||service!==this.data?.serviceId)return false;
      this.changes=data;return true;
    }catch(error){if(generation===this.changeGeneration)this.changeError=error.message;return false;}
    finally{if(generation===this.changeGeneration){this.changeBusy=false;this.changeRevision=(this.changeRevision??0)+1;this.onUpdate();}}
  }
  async approveGepa(id){return this.skillMutation(()=>this.request(`/api/v1/gepa/runs/${encodeURIComponent(id)}/approve`,{method:'POST',body:{expectedRevision:this.data.gepa.revision},timeoutMs:120000}),'gepa');}
  async activateGepa(id){return this.skillMutation(()=>this.request(`/api/v1/gepa/versions/${encodeURIComponent(id)}/activate`,{method:'POST',body:{expectedRevision:this.data.gepa.revision}}),'gepa');}
  async selectGepaRun(id){this.selectedGepaRun=id?validateGepaRun(await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}`)):null;this.onUpdate();}
  async selectLlmRun(id){this.selectedLlmRun=id?validateLlmRun(await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}`)):null;this.onUpdate(this.snapshot());}
  async selectSkillRun(id){
    this.selectedSkillRun=id?validateSkillRun(await this.request(`/api/v1/runtime/runs/${encodeURIComponent(id)}`)):null;
    this.onUpdate(this.snapshot());
  }
}
