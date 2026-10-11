import {agentsView,agentForm,relationshipForm} from './agent-view.js';

export function createAgentUI({api,render,toast,runtimeSnapshot=()=>null}){
  const view={selectedId:null,query:'',role:'all',pickedSkill:null};
  let editingId=null;
  const dialog=()=>document.querySelector('#agent-config');
  const show=html=>{dialog().innerHTML=html;dialog().showModal();};
  document.addEventListener('input',event=>{
    if(!event.target.matches('[data-agent-search]'))return;
    const cursor=event.target.selectionStart;
    view.query=event.target.value;
    render();
    const next=document.querySelector('[data-agent-search]');
    next?.focus({preventScroll:true});next?.setSelectionRange(cursor,cursor);
  });
  document.addEventListener('change',event=>{
    if(event.target.matches('[data-agent-role]')){
      view.role=event.target.value;render();document.querySelector('[data-agent-role]')?.focus({preventScroll:true});
    }
  });
  document.addEventListener('submit',event=>{
    if(!['agent-form','relationship-form'].includes(event.target.id))return;
    event.preventDefault();
    try{
      const f=new FormData(event.target);
      if(event.target.id==='agent-form'){
        const id=editingId||`AG-${crypto.randomUUID()}`;
        api.saveAgent({id,name:f.get('name').trim(),role:f.get('role'),runtime:f.get('runtime').trim(),model:f.get('model').trim(),memory:f.get('memory'),isolation:f.get('isolation'),maxSteps:Number(f.get('maxSteps')),temperature:Number(f.get('temperature')),tools:f.get('tools').split(/[,，]/).map(s=>s.trim()).filter(Boolean),skillIds:f.getAll('skills'),enabled:f.has('enabled'),connection:'disconnected'});
        view.selectedId=id;view.pickedSkill=null;view.query='';view.role='all';
        toast('已儲存代理人配置；尚未啟動 Runtime');
      }else{
        api.addRelationship({id:`LINK-${crypto.randomUUID()}`,from:f.get('from'),to:f.get('to'),type:f.get('type'),artifact:f.get('artifact').trim()});
        toast('已建立工作關係設定');
      }
      dialog().close();render();
    }catch(error){event.target.querySelector('.form-error').textContent=error.message;}
  });
  return {
    view(state){return agentsView(state,{...view,runtime:runtimeSnapshot()});},
    handleClick(button){
      const s=api.snapshot();
      if(button.dataset.agentSelect){view.selectedId=button.dataset.agentSelect;view.pickedSkill=null;render(true);return true;}
      if(button.dataset.agentSkill){view.pickedSkill=button.dataset.agentSkill;render(true);return true;}
      if(button.hasAttribute('data-agent-new')){editingId=null;show(agentForm());return true;}
      if(button.dataset.agentEdit){editingId=button.dataset.agentEdit;show(agentForm(s.registry.agents.find(a=>a.id===editingId)));return true;}
      if(button.dataset.agentDelete){
        if(window.confirm('刪除此代理人設定及其工作關係？此操作不會停止或刪除任何實際 Runtime。')){api.removeAgent(button.dataset.agentDelete);view.selectedId=null;view.pickedSkill=null;render();toast('已刪除代理人設定與相關工作關係');}return true;
      }
      if(button.hasAttribute('data-relation-new')){show(relationshipForm(s.registry));return true;}
      if(button.dataset.relationDelete){api.removeRelationship(button.dataset.relationDelete);render();toast('已刪除工作關係設定');return true;}
      return false;
    }
  };
}
