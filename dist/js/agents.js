// Browser-local role configuration, never runtime discovery or execution evidence.
export const ROLES = {coordinator:'協調與排程',worker:'任務執行',reflector:'技能反思',evaluator:'評估與驗證',reviewer:'版本檢閱'};
export const RELATION_TYPES = {task:'任務委派',evidence:'評估證據',feedback:'反思回饋',review:'版本檢閱'};
export const MEMORIES = {none:'不保留',session:'單次任務',snapshot:'固定記憶快照'};
export const ISOLATIONS = {workspace:'獨立工作目錄',container:'容器（規劃中）'};
export const SKILLS = [
  {id:'plan-evolution-run',name:'演化任務規劃',version:'S0',scope:'協調',evolvable:false,description:'分配固定預算，安排執行與評估順序。',body:'# Plan evolution run\n\n1. Freeze model, tools, memory and dataset revisions.\n2. Allocate the evaluation budget.\n3. Dispatch a task and collect evaluation evidence.\n4. Send improved candidates for review.'},
  {id:'python-fix-and-verify',name:'Python 修復與驗證',version:'S0 / S1',scope:'任務執行',evolvable:true,description:'第一輪演化目標：修復程式、執行測試並保留結果。',body:null},
  {id:'reflect-skill',name:'技能反思與候選產生',version:'S0',scope:'反思',evolvable:false,description:'依訓練失敗案例提出技能本文修改；GEPA adapter 尚未接入。',body:'# Reflect skill\n\n1. Inspect training traces and failure categories.\n2. Propose a minimal change to the target skill body.\n3. Keep runtime, model, tools and workflow fixed.\n4. Never inspect held-out tasks.'},
  {id:'evaluate-python',name:'Python 評估',version:'S0',scope:'評估',evolvable:false,description:'固定測試流程，回傳分數、測試輸出與隔離工作目錄。',body:'# Evaluate Python repair\n\n1. Run trusted tests in an isolated workspace.\n2. Record commands, exit codes and artifact references.\n3. Score with the fixed evaluator revision.\n4. Keep held-out evidence outside the reflection loop.'},
  {id:'review-release',name:'技能版本檢閱',version:'S0',scope:'檢閱',evolvable:false,description:'檢查改善證據與變更範圍，提出版本建議。',body:'# Review skill release\n\n1. Compare baseline and candidate evidence.\n2. Check skill scope and held-out results.\n3. Recommend approval only after completed evaluation.\n4. Require an authorized server-side release operation.'}
];
export function initialRegistry(){
  const agent=(id,name,role,runtime,skillIds,tools)=>({id,name,role,runtime,model:'未設定',memory:'snapshot',isolation:'workspace',maxSteps:20,temperature:0.2,enabled:true,connection:'disconnected',skillIds,tools});
  return {agents:[
    agent('AG-001','Orchestrator','coordinator','排程服務（規劃）',['plan-evolution-run'],['dispatch-task','read-evidence']),
    agent('AG-002','nanobot Worker','worker','nanobot（規劃）',['python-fix-and-verify'],['read-file','edit-file','run-tests']),
    agent('AG-003','Skill Reflector','reflector','GEPA adapter（規劃）',['reflect-skill'],['read-training-trace','propose-skill']),
    agent('AG-004','Evaluator','evaluator','Python evaluator（規劃）',['evaluate-python'],['run-trusted-tests','score-result']),
    agent('AG-005','Release Reviewer','reviewer','檢閱服務（規劃）',['review-release'],['read-evidence','recommend-release'])
  ],relationships:[
    {id:'LINK-001',from:'AG-001',to:'AG-002',type:'task',artifact:'任務、技能版本與固定執行設定'},
    {id:'LINK-002',from:'AG-002',to:'AG-004',type:'evidence',artifact:'程式變更、測試輸出與 trace'},
    {id:'LINK-003',from:'AG-004',to:'AG-003',type:'feedback',artifact:'訓練失敗案例；不含保留測試'},
    {id:'LINK-004',from:'AG-003',to:'AG-002',type:'feedback',artifact:'候選技能本文 S1'},
    {id:'LINK-005',from:'AG-004',to:'AG-005',type:'review',artifact:'基準與候選分數、最終檢閱證據'},
    {id:'LINK-006',from:'AG-005',to:'AG-001',type:'review',artifact:'版本建議；真實發布需後端授權'}
  ]};
}
const text=(v,max,allowEmpty=false)=>typeof v==='string'&&v.length<=max&&(allowEmpty||v.trim().length>0);
const id=v=>text(v,80)&&/^[A-Za-z0-9_-]+$/.test(v);
const list=(v,max,check)=>Array.isArray(v)&&v.length<=max&&new Set(v).size===v.length&&v.every(check);
export function validateRegistry(registry){
  if(!registry||!Array.isArray(registry.agents)||registry.agents.length>30||!Array.isArray(registry.relationships)||registry.relationships.length>120)throw Error('代理人設定格式不正確（最多 30 個代理人、120 個關係）');
  const ids=new Set(),skills=new Set(SKILLS.map(s=>s.id));
  for(const a of registry.agents){
    if(!a||!id(a.id)||ids.has(a.id)||!text(a.name,80)||!Object.hasOwn(ROLES,a.role)||!text(a.runtime,100)||!text(a.model,100)||!Object.hasOwn(MEMORIES,a.memory)||!Object.hasOwn(ISOLATIONS,a.isolation)||!Number.isInteger(a.maxSteps)||a.maxSteps<1||a.maxSteps>100||!Number.isFinite(a.temperature)||a.temperature<0||a.temperature>2||typeof a.enabled!=='boolean'||a.connection!=='disconnected'||!list(a.skillIds,SKILLS.length,s=>skills.has(s))||!list(a.tools,20,s=>text(s,80)))throw Error('代理人屬性不正確；展示設定不能宣告已連線或執行中');
    ids.add(a.id);
  }
  const links=new Set(),pairs=new Set();
  for(const r of registry.relationships){
    const pair=JSON.stringify([r?.from,r?.to,r?.type]);
    if(!r||!id(r.id)||links.has(r.id)||!ids.has(r.from)||!ids.has(r.to)||r.from===r.to||!Object.hasOwn(RELATION_TYPES,r.type)||pairs.has(pair)||!text(r.artifact,200))throw Error('工作關係不正確；請檢查端點、重複關係與交付內容');
    links.add(r.id);pairs.add(pair);
  }
  return registry;
}
export function registryStats(registry){
  validateRegistry(registry);
  return {total:registry.agents.length,enabled:registry.agents.filter(a=>a.enabled).length,connected:0,skills:new Set(registry.agents.flatMap(a=>a.skillIds)).size,relationships:registry.relationships.length};
}
export function filterAgents(registry,{query='',role='all'}={}){
  const q=query.trim().toLocaleLowerCase();
  return registry.agents.filter(a=>(role==='all'||a.role===role)&&[a.id,a.name,ROLES[a.role],a.runtime,a.model,...a.tools,...a.skillIds,...SKILLS.filter(s=>a.skillIds.includes(s.id)).map(s=>s.name)].join(' ').toLocaleLowerCase().includes(q));
}
export function saveAgent(registry,agent){
  const next=structuredClone(registry),index=next.agents.findIndex(a=>a.id===agent.id);
  if(index<0)next.agents.push(structuredClone(agent));else next.agents[index]=structuredClone(agent);
  return validateRegistry(next);
}
export function removeAgent(registry,id){
  if(!registry.agents.some(a=>a.id===id))throw Error('代理人不存在');
  return validateRegistry({agents:registry.agents.filter(a=>a.id!==id),relationships:registry.relationships.filter(r=>r.from!==id&&r.to!==id)});
}
export function addRelationship(registry,relationship){return validateRegistry({...registry,relationships:[...registry.relationships,structuredClone(relationship)]});}
export function removeRelationship(registry,id){
  if(!registry.relationships.some(r=>r.id===id))throw Error('工作關係不存在');
  return {...registry,relationships:registry.relationships.filter(r=>r.id!==id)};
}
