// Pure demo state machine. All evaluation values are synthetic, not model evidence.
export const BASE_SKILL = '# Python fix and verify\n\n1. Read the failing test and relevant code.\n2. Make the smallest repair.\n3. Run the tests and summarize the change.';
export const CANDIDATE_SKILL = '# Python fix and verify\n\n1. Reproduce the failure before editing.\n2. Read the relevant code and identify the root cause.\n3. Make the smallest repair; preserve public interfaces.\n4. Run targeted tests, then the full regression suite.\n5. Verify edge cases and report commands and results.';
export function newExperiment({name,budget=80,scenario='improve'}, id, now) {
  if(typeof name!=='string'||!name.trim()||name.length>80) throw Error('請輸入 1–80 字的實驗名稱');
  if(![40,80,120].includes(Number(budget))) throw Error('評估預算不受支援');
  if(!['improve','no-gain'].includes(scenario)) throw Error('展示情境不受支援');
  return {id,name:name.trim(),budget:Number(budget),scenario,createdAt:now,status:'queued',completed:0,mode:'demo',skill:'python-fix-and-verify',baseline:0.6,candidate:null,curve:[],events:[{at:now,text:'已建立展示實驗，等待啟動'}]};
}
export function transition(exp,action,now) {
  const allowed={start:['queued'],pause:['running'],resume:['paused'],cancel:['queued','running','paused']};
  if(!allowed[action]?.includes(exp.status)) throw Error('目前狀態無法執行此動作');
  const status={start:'running',pause:'paused',resume:'running',cancel:'cancelled'}[action];
  return {...exp,status,events:[...exp.events,{at:now,text:{start:'啟動模擬評估',pause:'已暫停',resume:'已繼續',cancel:'已取消'}[action]}]};
}
export function tick(exp,now) {
  if(exp.status!=='running') return exp;
  const completed=Math.min(exp.budget,exp.completed+Math.max(1,Math.ceil(exp.budget/16)));
  const progress=completed/exp.budget;
  const candidate=exp.scenario==='improve'?Math.min(0.8,0.6+Math.floor(progress*4)*0.05):0.6;
  const done=completed===exp.budget;
  return {...exp,completed,candidate,status:done?'completed':'running',curve:[...exp.curve,{evaluations:completed,score:Number(candidate.toFixed(2))}],events:done?[...exp.events,{at:now,text:'模擬評估完成；可檢閱驗證與保留測試示例'}]:exp.events};
}
export function canRelease(exp){return exp?.mode==='demo'&&exp.status==='completed'&&exp.candidate>exp.baseline;}
export function release(state,exp,now,id){
  if(!canRelease(exp)) throw Error('實驗需完成且候選必須改善，才能建立展示版本');
  if(state.releases.some(r=>r.experimentId===exp.id)) throw Error('此實驗已有展示版本');
  const r={id,label:`v0.${state.releases.length+1}.0-demo`,experimentId:exp.id,createdAt:now,body:CANDIDATE_SKILL,mode:'demo'};
  return {...state,releases:[r,...state.releases],activeReleaseId:r.id};
}
export function activate(state,id){if(id!=='baseline'&&!state.releases.some(r=>r.id===id)) throw Error('版本不存在');return {...state,activeReleaseId:id};}
export function initialState(){
  const e=newExperiment({name:'Python 修復技能 · 基準示例',budget:80},'DEMO-001','2026-10-11T06:00:00Z');
  let done=transition(e,'start',e.createdAt);while(done.status==='running') done=tick(done,e.createdAt);
  return {schemaVersion:1,mode:'demo',selectedId:e.id,experiments:[done],releases:[],activeReleaseId:'baseline'};
}
export function validateState(s){
  if(!s||s.schemaVersion!==1||s.mode!=='demo'||!Array.isArray(s.experiments)||s.experiments.length>100||!Array.isArray(s.releases)||s.releases.length>100) throw Error('僅接受本工作台匯出的展示資料（schemaVersion 1）');
  const ids=new Set();
  for(const e of s.experiments){
    newExperiment(e,e.id,e.createdAt);
    if(typeof e.id!=='string'||e.id.length>100||ids.has(e.id)||e.mode!=='demo'||e.skill!=='python-fix-and-verify'||!['queued','running','paused','cancelled','completed'].includes(e.status)||!Number.isInteger(e.completed)||e.completed<0||e.completed>e.budget||e.baseline!==0.6||!(e.candidate===null||typeof e.candidate==='number'&&e.candidate>=0&&e.candidate<=1)||!Array.isArray(e.curve)||e.curve.length>150||!Array.isArray(e.events)||e.events.length>500||!Number.isFinite(Date.parse(e.createdAt))) throw Error('實驗資料格式不正確');
    if(e.status==='completed'&&(e.completed!==e.budget||e.candidate===null)) throw Error('完成狀態與評估數不一致');
    if(e.curve.some(p=>!Number.isInteger(p.evaluations)||p.evaluations<0||p.evaluations>e.budget||!Number.isFinite(p.score)||p.score<0||p.score>1)||e.events.some(v=>typeof v.text!=='string'||v.text.length>500||!Number.isFinite(Date.parse(v.at)))) throw Error('曲線或事件資料不正確');
    ids.add(e.id);
  }
  const releases=new Set();const releasedExperiments=new Set();
  for(const r of s.releases){if(typeof r.id!=='string'||r.id==='baseline'||releases.has(r.id)||releasedExperiments.has(r.experimentId)||r.mode!=='demo'||typeof r.label!=='string'||r.label.length>80||typeof r.body!=='string'||r.body.length>20000||!Number.isFinite(Date.parse(r.createdAt))||!canRelease(s.experiments.find(e=>e.id===r.experimentId))) throw Error('版本資料不正確');releases.add(r.id);releasedExperiments.add(r.experimentId);}
  if(s.selectedId!==null&&!ids.has(s.selectedId)||s.activeReleaseId!=='baseline'&&!releases.has(s.activeReleaseId)) throw Error('選取的實驗或版本不存在');
  return s;
}
