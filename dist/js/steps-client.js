export function validateSteps(data){
 const time=t=>t===null||Number.isFinite(Date.parse(t));
 if(data?.schemaVersion!==1||!/^RUN-[A-Za-z0-9-]+$/.test(data.runId)||!['queued','running','completed','failed','cancelled','interrupted'].includes(data.runStatus)||!Array.isArray(data.steps)||data.steps.length>500||typeof data.truncated!=='boolean'||!Number.isInteger(data.returnedEvents)||data.returnedEvents<0||data.returnedEvents>500||!Number.isInteger(data.matchedEvents)||data.matchedEvents<data.returnedEvents||!time(data.serverTime))throw Error('步驟紀錄格式不正確');
 const ids=new Set();
 for(const s of data.steps){if(!/^[a-f0-9]{32}$/.test(s.id)||ids.has(s.id)||typeof s.name!=='string'||s.name.length>256||typeof s.module!=='string'||!['running','completed','failed','cancelled','interrupted','unreported'].includes(s.status)||!time(s.startedAt)||!time(s.finishedAt)||s.startedAt===null&&s.finishedAt===null||!(s.durationMs===null||Number.isFinite(s.durationMs)&&s.durationMs>=0)||s.error!==undefined&&s.error!==null&&typeof s.error!=='string')throw Error('步驟狀態或耗時不正確');ids.add(s.id);}
 return data;
}
export class StepsClient{
 constructor({request,onUpdate=()=>{}}){this.request=request;this.onUpdate=onUpdate;this.runId='';this.data=null;this.error=null;this.enabled=true;this.busy=false;this.generation=0;this.lastSuccess=null;}
 snapshot(){return {runId:this.runId,data:this.data,error:this.error,enabled:this.enabled,busy:this.busy,lastSuccess:this.lastSuccess};}
 async select(id){if(id&&!/^RUN-[A-Za-z0-9-]+$/.test(id))throw Error('Run ID 格式不正確');this.generation++;this.runId=id;this.data=null;this.error=null;this.busy=false;this.onUpdate();return this.refresh();}
 async refresh(){
  if(!this.runId||this.busy)return false;
  const generation=++this.generation,id=this.runId;this.busy=true;this.onUpdate();
  try{const data=validateSteps(await this.request(`/api/v1/debug/steps/${encodeURIComponent(id)}`));if(data.runId!==id)throw Error('步驟紀錄與所選 Run 不一致');if(generation!==this.generation)return false;this.data=data;this.error=null;this.lastSuccess=new Date().toISOString();return true;}
  catch(error){if(generation===this.generation)this.error=error.message;return false;}
  finally{if(generation===this.generation){this.busy=false;this.onUpdate();}}
 }
}
