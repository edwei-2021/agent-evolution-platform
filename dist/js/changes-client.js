export function validateChanges(data){
 const text=s=>s===null||typeof s==='string'&&new TextEncoder().encode(s).length<=8000;
 if(data?.schemaVersion!==1||!/^RUN-[A-Za-z0-9-]+$/.test(data.runId)||!['gepa-evolution','nanobot-repair'].includes(data.task)||!['queued','running','completed','failed','cancelled','interrupted'].includes(data.runStatus)||typeof data.verified!=='boolean'||data.historyOnly!==true||!Array.isArray(data.rollouts)||data.rollouts.length>20||!Array.isArray(data.skillHistory)||data.skillHistory.length>10||!Array.isArray(data.warnings)||data.warnings.length>100||data.warnings.some(s=>typeof s!=='string'||s.length>300)||!Number.isInteger(data.totalRollouts)||data.totalRollouts<0||data.totalRollouts>200||!Number.isInteger(data.offset)||data.offset<0||data.offset>200||data.limit!==20||typeof data.selectedRollout!=='string'||data.selectedRollout&&!/^R\d{4}$/.test(data.selectedRollout))throw Error('修改歷程格式不正確');
 for(const r of data.rollouts)if(!/^R\d{4}$/.test(r.id)||typeof r.completed!=='boolean'||![null,true,false].includes(r.skillChanged))throw Error('Rollout 歷程不正確');
 for(const s of data.skillHistory)if(!['baseline','proposal','selection','pending'].includes(s.kind)||!text(s.before)||!text(s.after)||typeof s.changed!=='boolean'||typeof s.note!=='string')throw Error('Skill 歷程不正確');
 if(data.trace){
  const t=data.trace;if(!text(t.baseline)||!text(t.currentSource)||!text(t.candidate)||!text(t.skill?.body??null)||!Array.isArray(t.steps)||t.steps.length>24)throw Error('原始碼歷程不正確');
  for(const s of t.steps)if(!Number.isInteger(s.id)||s.id<1||s.id>24||!['read_solution','write_solution','run_tests'].includes(s.name)||!['running','completed','failed'].includes(s.status)||!text(s.before)||!text(s.after)||!text(s.attemptedSource)||typeof s.applied!=='boolean'||typeof s.changed!=='boolean')throw Error('工具修改歷程不正確');
 }
 return data;
}
