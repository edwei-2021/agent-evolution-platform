export const COMPARISON_POLICY='paired-zero-regression-v1';
export const OUTCOME_LABELS={improved:'改善',regressed:'退步','retained-pass':'持續通過','retained-fail':'仍未通過'};
export const BLOCKER_LABELS={'unchanged-skill':'Skill 本文未變更','validation-not-improved':'獨立驗證總分未改善','heldout-total-regressed':'最終測試總分退步','validation-task-regressed':'獨立驗證有原本通過的題目退步','heldout-task-regressed':'最終測試有原本通過的題目退步'};
const outcomes=['retained-fail','improved','regressed','retained-pass'];
const splits=['validation','heldout'];
const fail=()=>{throw Error('GEPA 逐題比較與證據不一致');};

export function validatePairedComparison(c,r){
 if(c.comparisonPolicy===undefined){if(r.comparison!==undefined||r.releaseBlockers!==undefined)fail();return null;}
 const p=r.comparison;
 if(c.comparisonPolicy!==COMPARISON_POLICY||p?.policy!==c.comparisonPolicy||!Array.isArray(p.tasks)||p.tasks.length!==c.counts.validation+c.counts.heldout||p.tasks.length>30)fail();
 const ids=new Set(),rollouts=new Set();
 const counts=Object.fromEntries(splits.map(s=>[s,Object.fromEntries(outcomes.map(o=>[o,0]))]));
 for(const row of p.tasks){
  if(!row||!splits.includes(row.split)||typeof row.taskId!=='string'||!/^(CH|PY)-[A-Za-z0-9-]{1,120}$/.test(row.taskId)||ids.has(row.taskId)||!Number.isInteger(row.baseline)||!Number.isInteger(row.selected)||![0,1].includes(row.baseline)||![0,1].includes(row.selected)||row.outcome!==outcomes[2*row.baseline+row.selected]||typeof row.group!=='string'||row.group.length>120)fail();
  ids.add(row.taskId);
  for(const key of ['baselineRolloutId','selectedRolloutId']){if(!/^R\d{4}$/.test(row[key])||rollouts.has(row[key]))fail();rollouts.add(row[key]);}
  if(c.profile==='bank'){
   const frozen=c.datasetSnapshot?.data?.[row.split]?.find(t=>t.id===row.taskId);
   if(!frozen||['group','difficulty','topic'].some(k=>row[k]!==frozen[k]))fail();
  }
  counts[row.split][row.outcome]++;
 }
 for(const s of splits){
  if(!p.splits?.[s]||outcomes.some(o=>p.splits[s][o]!==counts[s][o]))fail();
  const n=counts[s];
  if(Object.values(n).reduce((a,b)=>a+b,0)!==c.counts[s]||n.regressed+n['retained-pass']!==r.final.baseline[s].passed||n.improved+n['retained-pass']!==r.final.selected[s].passed)fail();
 }
 const blockers=[];
 if(r.selectedSkill.hash===r.baselineSkill.hash)blockers.push('unchanged-skill');
 if(r.final.selected.validation.passed<=r.final.baseline.validation.passed)blockers.push('validation-not-improved');
 if(r.final.selected.heldout.passed<r.final.baseline.heldout.passed)blockers.push('heldout-total-regressed');
 for(const s of splits)if(counts[s].regressed)blockers.push(`${s}-task-regressed`);
 if(!Array.isArray(r.releaseBlockers)||JSON.stringify(r.releaseBlockers)!==JSON.stringify(blockers))fail();
 return blockers;
}
