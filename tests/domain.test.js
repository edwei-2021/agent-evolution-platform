import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState,newExperiment,transition,tick,canRelease,release,activate,validateState} from '../dist/js/domain.js';
import {DemoAdapter} from '../dist/js/adapter.js';
const now='2026-10-11T06:00:00Z';
const create=(scenario='improve',budget=80)=>newExperiment({name:'Test',budget,scenario},'TEST',now);
function finish(e){e=transition(e,'start',now);while(e.status==='running')e=tick(e,now);return e;}
const storage=()=>{const map=new Map();return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};};
test('pause prevents progress, resume continues, and terminal actions are rejected',()=>{
 let e=tick(transition(create(),'start',now),now);const count=e.completed;
 e=transition(e,'pause',now);assert.equal(tick(e,now).completed,count);
 e=transition(e,'resume',now);assert.ok(tick(e,now).completed>count);
 e=transition(e,'cancel',now);assert.equal(tick(e,now),e);assert.throws(()=>transition(e,'resume',now));
});
test('all budgets terminate exactly at the cap',()=>{for(const budget of [40,80,120]){const e=finish(create('improve',budget));assert.equal(e.completed,budget);assert.equal(e.status,'completed');assert.equal(e.candidate,.8);}});
test('no gain keeps baseline and rejects release',()=>{const e=finish(create('no-gain'));assert.equal(e.candidate,e.baseline);assert.equal(canRelease(e),false);assert.throws(()=>release(initialState(),e,now,'r'));});
test('incomplete, cancelled, and non-demo evidence cannot create demo releases',()=>{for(const status of ['queued','running','paused','cancelled'])assert.equal(canRelease({...finish(create()),status}),false);assert.equal(canRelease({...finish(create()),mode:'real'}),false);});
test('release can be activated and rolled back, without duplicate release',()=>{const s=initialState(),e=s.experiments[0];const next=release(s,e,now,'r');assert.equal(next.activeReleaseId,'r');assert.equal(activate(next,'baseline').activeReleaseId,'baseline');assert.throws(()=>release(next,e,now,'r2'));assert.throws(()=>activate(next,'absent'));assert.equal(s.releases.length,0);});
test('configuration rejects unsupported budgets and scenarios',()=>{assert.throws(()=>newExperiment({name:' ',budget:80},'x',now));assert.throws(()=>newExperiment({name:'a',budget:1},'x',now));assert.throws(()=>newExperiment({name:'a',scenario:'real'},'x',now));});
test('export round trip preserves selected experiment and releases',()=>{const s=initialState();const r=release(s,s.experiments[0],now,'r');assert.deepEqual(validateState(JSON.parse(JSON.stringify(r))),r);});
test('import rejects broken completion and release references',()=>{const s=initialState();s.experiments[0].completed=1;assert.throws(()=>validateState(s));const t=initialState();t.activeReleaseId='absent';assert.throws(()=>validateState(t));});
test('import rejects duplicate experiments and invalid chart samples',()=>{const s=initialState();s.experiments.push(structuredClone(s.experiments[0]));assert.throws(()=>validateState(s));const t=initialState();t.experiments[0].curve[0].score=5;assert.throws(()=>validateState(t));});
test('import cannot label non-demo evaluation data as real results',()=>{const s=initialState();s.mode='real';assert.throws(()=>validateState(s));const t=initialState();t.experiments[0].mode='real';assert.throws(()=>validateState(t));});
test('reload pauses active demo experiments and preserves progress',()=>{const db=storage(),a=new DemoAdapter(db);a.create({name:'Run',budget:40});a.action('start');a.tick();const e=a.snapshot().experiments[0];const b=new DemoAdapter(db);assert.equal(b.snapshot().experiments[0].status,'paused');assert.equal(b.snapshot().experiments[0].completed,e.completed);});
test('import pauses running experiments and rejects invalid data atomically',()=>{const a=new DemoAdapter(storage());const s=initialState();s.experiments=[transition(create(),'start',now)];s.selectedId='TEST';a.import(s);assert.equal(a.snapshot().experiments[0].status,'paused');const before=a.snapshot();assert.throws(()=>a.import({}));assert.deepEqual(a.snapshot(),before);});
test('unavailable storage exposes persistence error while retaining usable state',()=>{const a=new DemoAdapter({getItem(){return null;},setItem(){throw Error('quota');}});a.create({name:'Test'});assert.equal(a.persistenceError,true);assert.equal(a.snapshot().experiments.length,2);});
test('malformed saved data recovers to demo and exposes warning',()=>{const a=new DemoAdapter({getItem(){return '{';},setItem(){}});assert.equal(a.recoveryWarning,true);assert.equal(a.snapshot().mode,'demo');});
