export function validateLogs(value){
 if(!value||value.schemaVersion!==1||!Array.isArray(value.records)||value.records.length>500||!Number.isInteger(value.retained)||!Number.isInteger(value.matched)||!Array.isArray(value.modules)||!Array.isArray(value.levels)||value.modules.some(m=>!['api','gui','runtime','ollama','llm','skills','nanobot','coordinator','worker','reflector','evaluator','reviewer'].includes(m))||value.levels.some(l=>!['DEBUG','INFO','WARNING','ERROR'].includes(l)))throw Error('Log API 資料格式不正確');
 let prior=Infinity;
 for(const r of value.records){if(!Number.isInteger(r.id)||r.id<1||r.id>=prior||!Number.isFinite(Date.parse(r.at))||!value.modules.includes(r.module)||!value.levels.includes(r.level)||typeof r.message!=='string'||r.message.length>2048||!r.details||typeof r.details!=='object'||Array.isArray(r.details))throw Error('Log 紀錄格式不正確');prior=r.id;}
 if(value.nextBefore!==null&&(!value.records.length||value.nextBefore!==value.records.at(-1).id))throw Error('Log 分頁游標不正確');
 return value;
}
export class LogsClient{
 constructor({request,onUpdate=()=>{}}){this.request=request;this.onUpdate=onUpdate;this.data=null;this.error=null;this.busy=false;this.enabled=true;this.lastSuccess=null;this.filters={module:'',level:'',q:'',runId:''};this.generation=0;this.raw=null;this.rawError=null;this.rawBusy=false;this.rawGeneration=0;this.rawRun='';}
 snapshot(){return {data:this.data,error:this.error,busy:this.busy,enabled:this.enabled,lastSuccess:this.lastSuccess,filters:{...this.filters},raw:this.raw,rawError:this.rawError,rawBusy:this.rawBusy,rawRun:this.rawRun};}
 async refresh(older=false){
  if(this.busy)return false;
  const generation=++this.generation,query=new URLSearchParams({...this.filters,limit:'100'});
  if(older&&this.data?.nextBefore)query.set('before',this.data.nextBefore);
  else if(older)return false;
  this.busy=true;this.onUpdate();
  try{
   const page=validateLogs(await this.request('/api/v1/debug/logs?'+query));
   if(generation!==this.generation)return false;
   if(older){this.enabled=false;page.records=[...(this.data?.records||[]),...page.records].slice(0,1000);if(page.records.length===1000)page.nextBefore=null;}
   this.data=page;this.error=null;this.lastSuccess=new Date().toISOString();return true;
  }catch(error){if(generation===this.generation)this.error=error.message;return false;}
  finally{if(generation===this.generation){this.busy=false;this.onUpdate();}}
 }
 async filter(values){this.generation++;this.busy=false;this.filters={...this.filters,...values};this.data=null;return this.refresh();}
 selectRawRun(id){this.rawGeneration++;this.rawRun=id;this.raw=null;this.rawError=null;this.rawBusy=false;this.onUpdate();}
 async readRole(role){
  if(!this.rawRun||!['coordinator','worker','reflector','evaluator','reviewer'].includes(role))return false;
  const generation=++this.rawGeneration;this.rawBusy=true;this.rawError=null;this.onUpdate();
  try{
   const raw=await this.request(`/api/v1/debug/runs/${encodeURIComponent(this.rawRun)}/${role}`);
   if(generation!==this.rawGeneration)return false;
   if(typeof raw.content!=='string'||raw.content.length>200000||typeof raw.truncated!=='boolean')throw Error('原始 Log 格式不正確');
   this.raw=raw;return true;
  }catch(error){if(generation===this.rawGeneration)this.rawError=error.message;return false;}
  finally{if(generation===this.rawGeneration){this.rawBusy=false;this.onUpdate();}}
 }
 export(){return (this.data?.records||[]).map(r=>JSON.stringify(r)).join('\n')+'\n';}
}
