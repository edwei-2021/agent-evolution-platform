import {initialState,validateState,transition,tick,newExperiment,release,activate} from './domain.js';
const KEY='evolution-lab.demo.v1';
// Adapter boundary: replace this browser-local implementation with an authenticated service.
export class DemoAdapter {
  constructor(storage){this.storage=storage;this.persistenceError=false;this.recoveryWarning=false;try {const saved=storage.getItem(KEY);this.state=saved?validateState(JSON.parse(saved)):initialState();} catch {this.state=initialState();this.recoveryWarning=true;}this.state.experiments=this.state.experiments.map(e=>e.status==='running'?{...e,status:'paused'}:e);}
  snapshot(){return structuredClone(this.state);}
  save(next){validateState(next);this.state=next;try{this.storage.setItem(KEY,JSON.stringify(next));this.persistenceError=false;}catch{this.persistenceError=true;}return this.snapshot();}
  create(config){const e=newExperiment(config,`EXP-${Date.now()}-${Math.random().toString(16).slice(2,6)}`,new Date().toISOString());return this.save({...this.state,selectedId:e.id,experiments:[e,...this.state.experiments]});}
  select(id){return this.save({...this.state,selectedId:id});}
  action(action){const now=new Date().toISOString();return this.save({...this.state,experiments:this.state.experiments.map(e=>e.id===this.state.selectedId?transition(e,action,now):e)});}
  tick(){if(!this.state.experiments.some(e=>e.status==='running'))return false;this.save({...this.state,experiments:this.state.experiments.map(e=>tick(e,new Date().toISOString()))});return true;}
  release(){return this.save(release(this.state,this.state.experiments.find(e=>e.id===this.state.selectedId),new Date().toISOString(),`REL-${Date.now()}`));}
  activate(id){return this.save(activate(this.state,id));}
  import(data){validateState(data);const next=structuredClone(data);next.experiments=next.experiments.map(e=>e.status==='running'?{...e,status:'paused'}:e);return this.save(next);}
}
