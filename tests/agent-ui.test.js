import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgentUI} from '../dist/js/agent-ui.js';
import {DemoAdapter} from '../dist/js/adapter.js';

function harness(run){
  const previous={document:globalThis.document,window:globalThis.window,FormData:globalThis.FormData};
  const listeners={},errors={textContent:''},dialog={innerHTML:'',opened:false,showModal(){this.opened=true;},close(){this.opened=false;}};
  globalThis.document={addEventListener(type,fn){listeners[type]=fn;},querySelector(){return dialog;}};
  globalThis.window={confirm(){return true;}};
  globalThis.FormData=class {constructor(form){return form.fields;}};
  const api=new DemoAdapter({getItem(){return null;},setItem(){}});
  const ui=createAgentUI({api,render(){},toast(){}});
  const button=(dataset,attribute)=>({dataset,hasAttribute(name){return name===attribute;}});
  const submit=(id,values)=>{
    const fields=new Map(Object.entries(values));fields.getAll=key=>fields.get(key)||[];
    listeners.submit({preventDefault(){},target:{id,fields,querySelector(){return errors;}}});
  };
  try{run({api,ui,button,submit,dialog,errors});}finally{for(const [key,value]of Object.entries(previous)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
}
const config={name:'Configured Worker',role:'worker',runtime:'nanobot',model:'example-model',memory:'snapshot',isolation:'workspace',maxSteps:'25',temperature:'0.3',tools:'read-file, run-tests',skills:['python-fix-and-verify'],enabled:'on'};

test('agent dialog submission creates metadata and edit preserves ID without activating Runtime',()=>harness(({api,ui,button,submit,dialog})=>{
  ui.handleClick(button({},'data-agent-new'));
  assert.equal(dialog.opened,true);
  submit('agent-form',config);
  assert.equal(dialog.opened,false);
  const agent=api.snapshot().registry.agents.at(-1);
  assert.equal(agent.name,config.name);assert.equal(agent.connection,'disconnected');assert.equal(agent.maxSteps,25);
  ui.handleClick(button({agentEdit:agent.id}));
  submit('agent-form',{...config,name:'Edited Worker'});
  assert.equal(api.snapshot().registry.agents.length,6);
  assert.equal(api.snapshot().registry.agents.at(-1).id,agent.id);
  assert.equal(api.snapshot().registry.agents.at(-1).name,'Edited Worker');
}));
test('relationship form reports an invalid self link without closing and accepts a valid handoff',()=>harness(({api,ui,button,submit,dialog,errors})=>{
  ui.handleClick(button({},'data-relation-new'));
  const before=api.snapshot();
  submit('relationship-form',{from:'AG-001',to:'AG-001',type:'task',artifact:'handoff'});
  assert.ok(errors.textContent);assert.equal(dialog.opened,true);assert.deepEqual(api.snapshot(),before);
  submit('relationship-form',{from:'AG-001',to:'AG-003',type:'task',artifact:'training task'});
  assert.equal(dialog.opened,false);assert.equal(api.snapshot().registry.relationships.length,7);
}));
test('confirmed agent deletion cleans incident links and view selection remains renderable',()=>harness(({api,ui,button})=>{
  ui.handleClick(button({agentSelect:'AG-004'}));
  ui.handleClick(button({agentDelete:'AG-004'}));
  assert.equal(api.snapshot().registry.agents.length,4);
  assert.ok(api.snapshot().registry.relationships.every(r=>r.from!=='AG-004'&&r.to!=='AG-004'));
  assert.match(ui.view(api.snapshot()),/代理人與工作關係/);
}));
