export function validateBank(data){
 if(data?.schemaVersion!==1||!['python-challenges-v1','python-challenges-v2'].includes(data.version)||!Number.isInteger(data.revision)||data.revision<1||!Array.isArray(data.questions)||data.questions.length>100)throw Error('題庫格式不正確');
 const ids=new Set();for(const q of data.questions){
  if(!/^CH-[A-Za-z0-9-]{1,80}$/.test(q.id)||ids.has(q.id)||!['easy','medium','hard'].includes(q.difficulty)||!['train','validation','heldout'].includes(q.split)||typeof q.enabled!=='boolean'||['title','topic','group','prompt','baseline','reference','attribution'].some(k=>typeof q[k]!=='string')||!Array.isArray(q.visible)||!Array.isArray(q.hidden)||!Array.isArray(q.sources))throw Error('題目資料不正確');ids.add(q.id);
 }return data;
}
const editFields=q=>({...q,visible:JSON.stringify(q.visible,null,2),hidden:JSON.stringify(q.hidden,null,2),sources:q.sources.join('\n')});
export class ChallengesClient{
 constructor({request,onUpdate=()=>{}}){this.request=request;this.onUpdate=onUpdate;this.data=null;this.draft=null;this.selectedId='';this.busy=false;this.error=null;this.filter='all';}
 snapshot(){return {data:this.data,draft:this.draft,selectedId:this.selectedId,busy:this.busy,error:this.error,filter:this.filter};}
 async load(){if(this.busy)return;this.busy=true;this.error=null;this.onUpdate();try{this.data=validateBank(await this.request('/api/v1/challenges'));}catch(e){this.error=e.message;}finally{this.busy=false;this.onUpdate();}}
 select(id){const q=this.data?.questions.find(q=>q.id===id);if(!q)throw Error('題目不存在');this.selectedId=id;this.draft=editFields(q);this.error=null;this.onUpdate();}
 create(){this.selectedId='';this.draft=editFields({title:'',difficulty:'medium',topic:'',group:'custom-'+crypto.randomUUID(),split:'train',enabled:true,prompt:'',baseline:'def solve(data):\n    return data\n',reference:'def solve(data):\n    return data\n',visible:[{input:[1,2],expected:[1,2]},{input:[],expected:[]}],hidden:[{input:[3],expected:[3]},{input:[2,1],expected:[2,1]}],sources:[],attribution:'User-authored repair challenge.'});this.error=null;this.onUpdate();}
 edit(name,value){if(this.draft)this.draft[name]=value;}
 async save(){
  if(this.busy||!this.data||!this.draft)throw Error('請先載入題庫並選擇題目');
  const question={...this.draft};delete question.id;
  try{question.visible=JSON.parse(question.visible);question.hidden=JSON.parse(question.hidden);}catch{throw Error('公開與保留測試必須是有效 JSON 陣列');}
  question.sources=question.sources.split('\n').map(s=>s.trim()).filter(Boolean);
  this.busy=true;this.error=null;this.onUpdate();
  try{const path=this.selectedId?`/api/v1/challenges/${encodeURIComponent(this.selectedId)}/save`:'/api/v1/challenges';this.data=validateBank(await this.request(path,{method:'POST',body:{expectedRevision:this.data.revision,challenge:question},timeoutMs:15000}));this.draft=null;this.selectedId='';return true;}
  catch(e){this.error=e.message;return false;}finally{this.busy=false;this.onUpdate();}
 }
 async remove(id){if(this.busy||!this.data)return false;this.busy=true;this.error=null;this.onUpdate();try{this.data=validateBank(await this.request(`/api/v1/challenges/${encodeURIComponent(id)}/delete`,{method:'POST',body:{expectedRevision:this.data.revision}}));if(this.selectedId===id){this.draft=null;this.selectedId='';}return true;}catch(e){this.error=e.message;return false;}finally{this.busy=false;this.onUpdate();}}
 async installV2(){if(this.busy||!this.data)return false;this.busy=true;this.error=null;this.onUpdate();try{this.data=validateBank(await this.request('/api/v1/challenges/presets/repair-v2',{method:'POST',body:{expectedRevision:this.data.revision},timeoutMs:90000}));this.draft=null;this.selectedId='';return true;}catch(e){this.error=e.message;return false;}finally{this.busy=false;this.onUpdate();}}
}
