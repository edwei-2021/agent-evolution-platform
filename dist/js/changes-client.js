const boundedText=(s,max=1000)=>s===null||typeof s==='string'&&s.length<=max;
const count=(n,max)=>Number.isInteger(n)&&n>=0&&n<=max;
function question(q){
 if(!q||!['train','validation','heldout'].includes(q.split)||!['easy','medium','hard'].includes(q.difficulty)||!count(q.attempts,200)||['id','title','topic'].some(k=>!boundedText(q[k])||q[k]===null))throw Error('題目紀錄格式不正確');
}
function validateRecord(r){
 if(!(r.attempt===null||count(r.attempt,200)&&r.attempt>0))throw Error('同題嘗試次數不正確');
 if(r.question!==null)question(r.question);
 const v=r.records,s=v?.skill,w=v?.writes,e=v?.evaluation;
 if(!v||!s||!boundedText(s.name)||!(s.hash===null||/^[a-f0-9]{64}$/.test(s.hash))||!(s.label===null||s.label==='baseline'||/^P\d{3}$/.test(s.label)))throw Error('使用 Skill 紀錄不正確');
 if(w!==null&&(!w||['attempted','applied','rejected'].some(k=>!count(w[k],24))||!(w.changed===null||count(w.changed,24))||w.applied+w.rejected>w.attempted||(w.changed!==null&&w.changed>w.applied)))throw Error('寫入次數紀錄不正確');
 if(e!==null){
  if(!e||typeof e.repairPassed!=='boolean'||!count(e.calls,12)||!count(e.toolCalls,24)||!boundedText(e.taskOutcome,100)||!boundedText(e.sdkStopReason,100))throw Error('獨立測試紀錄不正確');
  for(const phase of ['baseline','candidate'])for(const split of ['visible','hidden']){
   const m=e[phase]?.[split];if(m!==null&&(!m||!count(m.passed,100)||!count(m.total,100)||m.passed>m.total))throw Error('測試數紀錄不正確');
  }
 }
}
export function validateChanges(data){
 const text=s=>s===null||typeof s==='string'&&new TextEncoder().encode(s).length<=8000;
 if(data?.schemaVersion!==1||!/^RUN-[A-Za-z0-9-]+$/.test(data.runId)||!['gepa-evolution','nanobot-repair'].includes(data.task)||!['queued','running','completed','failed','cancelled','interrupted'].includes(data.runStatus)||typeof data.verified!=='boolean'||data.historyOnly!==true||!Array.isArray(data.rollouts)||data.rollouts.length>20||!Array.isArray(data.skillHistory)||data.skillHistory.length>10||!Array.isArray(data.warnings)||data.warnings.length>100||data.warnings.some(s=>typeof s!=='string'||s.length>300)||!Number.isInteger(data.totalRollouts)||data.totalRollouts<0||data.totalRollouts>200||!Number.isInteger(data.offset)||data.offset<0||data.offset>200||data.limit!==20||typeof data.selectedRollout!=='string'||data.selectedRollout&&!/^R\d{4}$/.test(data.selectedRollout))throw Error('修改歷程格式不正確');
 for(const r of data.rollouts)if(!/^R\d{4}$/.test(r.id)||typeof r.completed!=='boolean'||![null,true,false].includes(r.skillChanged))throw Error('Rollout 歷程不正確');
 for(const r of data.rollouts)if(r.records!==undefined)validateRecord(r);
 if(data.taskCatalog!==undefined){
  const c=data.taskCatalog;
  if(!c||!Array.isArray(c.tasks)||c.tasks.length>50||!count(c.unassignedRollouts,200)||!(c.revision===null||count(c.revision,Number.MAX_SAFE_INTEGER))||!boundedText(c.version)||!(c.hash===null||/^[a-f0-9]{64}$/.test(c.hash)))throw Error('凍結題庫目錄不正確');
  c.tasks.forEach(question);
 }
 for(const s of data.skillHistory)if(!['baseline','proposal','selection','pending'].includes(s.kind)||!text(s.before)||!text(s.after)||typeof s.changed!=='boolean'||typeof s.note!=='string')throw Error('Skill 歷程不正確');
 if(data.trace){
  const t=data.trace;if(!text(t.baseline)||!text(t.currentSource)||!text(t.candidate)||!text(t.skill?.body??null)||!Array.isArray(t.steps)||t.steps.length>24)throw Error('原始碼歷程不正確');
  for(const s of t.steps)if(!Number.isInteger(s.id)||s.id<1||s.id>24||!['read_solution','write_solution','run_tests'].includes(s.name)||!['running','completed','failed'].includes(s.status)||!text(s.before)||!text(s.after)||!text(s.attemptedSource)||typeof s.applied!=='boolean'||typeof s.changed!=='boolean')throw Error('工具修改歷程不正確');
 }
 return data;
}
