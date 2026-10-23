export class MatrixClient {
  constructor({request,onUpdate=()=>{}}){this.request=request;this.onUpdate=onUpdate;this.jobs=[];this.selected=null;this.busy=false;this.error=null;}
  async refresh(){
    if(this.busy)return;
    this.busy=true;
    try{
      const listing=await this.request('/api/v1/tests/matrix');
      if(!Array.isArray(listing.jobs))throw Error('測試工作清單格式不正確');
      this.jobs=listing.jobs;
      const id=this.selected?.id||this.jobs[0]?.id;
      this.selected=id?await this.request(`/api/v1/tests/matrix/${encodeURIComponent(id)}`):null;
      this.error=null;
    }catch(error){this.error=error.message;}
    finally{this.busy=false;this.onUpdate();}
  }
  async start(){
    const job=await this.request('/api/v1/tests/matrix',{method:'POST',body:{}});
    this.selected=job;await this.refresh();return job;
  }
  async cancel(){
    if(!this.selected)throw Error('沒有可取消的測試');
    await this.request(`/api/v1/tests/matrix/${encodeURIComponent(this.selected.id)}/cancel`,{method:'POST',body:{}});
    await this.refresh();
  }
  async select(id){this.selected={id};await this.refresh();}
}
