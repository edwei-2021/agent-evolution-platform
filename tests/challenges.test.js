import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {ChallengesClient,validateBank} from '../dist/js/challenges-client.js';
import {challengesView} from '../dist/js/challenges-view.js';
import {RuntimeClient} from '../dist/js/runtime-client.js';
import {gepaView} from '../dist/js/gepa-view.js';
import {gepaPlan} from '../dist/js/gepa-plan.js';
const seeds=JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v1.json',import.meta.url)));
const bank=()=>({schemaVersion:1,version:'python-challenges-v1',revision:1,questions:structuredClone(seeds)});
const v2=JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v2.json',import.meta.url)));
const v3=JSON.parse(fs.readFileSync(new URL('../data/python-challenges-v3.json',import.meta.url)));

test('sixty-question V3 catalog has 20 per difficulty and an explicit batch submission',async()=>{
 assert.equal(v3.length,60);for(const level of ['easy','medium','hard'])assert.equal(v3.filter(q=>q.difficulty===level).length,20);
 const calls=[];let fail=true;
 const client=new ChallengesClient({request:async(path,options)=>{calls.push({path,options});if(!options)return bank();if(fail)throw Error('Revision conflict');return {...bank(),version:'python-challenges-v3',revision:2,questions:[...seeds.map(q=>({...q,enabled:false})),...v3]};}});
 await client.load();client.create();client.edit('title','Keep draft');client.v3Batch=4;
 assert.match(challengesView(client.snapshot()),/初階、中階、進階各 20 題/);assert.equal(calls.length,1);
 assert.equal(await client.installV3(),false);assert.equal(client.draft.title,'Keep draft');
 fail=false;assert.equal(await client.installV3(),true);assert.equal(client.draft,null);
 assert.equal(calls[2].path,'/api/v1/challenges/presets/repair-v3');assert.equal(calls[2].options.timeoutMs,360000);
 assert.deepEqual(calls[2].options.body,{expectedRevision:1,batch:4});
 assert.equal(client.data.version,'python-challenges-v3');assert.match(challengesView(client.snapshot()),/啟用所選批次/);
});

test('V2 preset is explicit, revisioned and preserves drafts on failure; viewing never installs',async()=>{
 const calls=[];let fail=true;
 const client=new ChallengesClient({request:async(path,options)=>{calls.push({path,options});if(!options)return bank();if(fail)throw Error('Revision conflict');return {...bank(),version:'python-challenges-v2',revision:2,questions:[...seeds.map(q=>({...q,enabled:false})),...v2]};}});
 await client.load();client.create();client.edit('title','Unsaved draft');
 assert.match(challengesView(client.snapshot()),/data-bank-v2/);assert.equal(calls.length,1);
 assert.equal(await client.installV2(),false);assert.equal(client.draft.title,'Unsaved draft');
 fail=false;assert.equal(await client.installV2(),true);assert.equal(client.draft,null);
 assert.equal(calls[2].path,'/api/v1/challenges/presets/repair-v2');
 assert.deepEqual(calls[2].options.body,{expectedRevision:1});assert.equal(calls[2].options.timeoutMs,90000);
 assert.equal(client.data.version,'python-challenges-v2');
 assert.match(challengesView(client.snapshot()),/data-bank-v2 disabled/);
 assert.throws(()=>validateBank({...bank(),version:'unknown'}),/格式/);
});

test('bank preparation selects the profile, clears historical selection and preserves uncertain submissions',()=>{
 const client=new RuntimeClient({fetcher:()=>{throw Error('Preparation must not make requests');}});
 client.selectedGepaRun={id:'RUN-old-selection'};client.prepareChallengeGepa();
 assert.equal(client.gepaProfile,'bank');assert.equal(client.selectedGepaRun,null);assert.equal(client.gepaTaskCalls,10);
 const pending={requestId:'frozen-fixture-request',profile:'smoke',maxSeconds:1800};
 client.pendingGepaSubmission=pending;assert.throws(()=>client.prepareChallengeGepa(),/上一筆 GEPA/);
 assert.equal(client.pendingGepaSubmission,pending);
 client.pendingGepaSubmission=null;client.actionBusy=true;assert.throws(()=>client.prepareChallengeGepa(),/上一筆 GEPA/);
});

test('Full and bank expose their different output-cap gates next to Start, including the exact threshold',()=>{
 const client=new RuntimeClient({fetcher:()=>{throw Error('Rendering must not make requests');}});
 client.data={gepa:{sdk:{available:true},optimizer:{available:true},versions:[],runs:[]},challenges:{revision:1,ready:true,counts:{train:6,validation:3,heldout:3}},provider:{config:{maxTokens:256}}};
 client.capabilities={};client.enabled=true;
 client.setGepaProfile('full');assert.doesNotMatch(gepaView(client.snapshot()),/data-gepa-start[^>]*disabled/);
 client.setGepaProfile('bank');let html=gepaView(client.snapshot());
 assert.match(html,/data-gepa-start[^>]*aria-describedby="gepa-start-blockers"[^>]*disabled/);
 assert.match(html,/目前已儲存的最大輸出 tokens：256/);assert.match(html,/data-page="integrations"/);
 assert.ok(html.indexOf('data-gepa-start-blockers')<html.indexOf('data-gepa-results'));
 client.data.provider.config.maxTokens=511;assert.match(gepaView(client.snapshot()),/data-gepa-start[^>]*disabled/);
 for(const cap of [512,1024]){client.data.provider.config.maxTokens=cap;html=gepaView(client.snapshot());assert.doesNotMatch(html,/data-gepa-start[^>]*disabled/);assert.doesNotMatch(html,/data-gepa-start-blockers/);}
 client.data.challenges.ready=false;client.data.challenges.error='Related groups cross splits <example>';
 html=gepaView(client.snapshot());assert.match(html,/data-gepa-start[^>]*disabled/);assert.match(html,/Related groups cross splits &lt;example&gt;/);assert.match(html,/data-page="challenges"/);
});

test('twelve original challenges expose three difficulties, separate splits, source links and escaped editors',()=>{
 const data=validateBank(bank());assert.equal(data.questions.length,12);assert.equal(new Set(data.questions.map(q=>q.difficulty)).size,3);
 const client=new ChallengesClient({request:async()=>data});client.data=data;client.select(data.questions[0].id);client.edit('prompt','<script>bad</script>');
 const html=challengesView(client.snapshot());assert.match(html,/公開測試 JSON/);assert.match(html,/參考解答/);assert.match(html,/保留測試 JSON/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 client.filter='hard';const filtered=challengesView({...client.snapshot(),draft:null});assert.match(filtered,/二分搜尋/);assert.doesNotMatch(filtered,/空白正規化/);
});
test('new/edit actions stay local; saves submit expected revision and preserve invalid drafts for correction',async()=>{
 const calls=[],client=new ChallengesClient({request:async(path,options)=>{calls.push({path,options});if(options)throw Error('Reference solution must pass');return bank();}});
 await client.load();client.create();client.edit('title','New task');client.edit('reference','def solve(data):\n    return data\n');
 assert.equal(calls.length,1);assert.equal(await client.save(),false);assert.equal(calls[1].path,'/api/v1/challenges');assert.equal(calls[1].options.body.expectedRevision,1);
 assert.equal(client.draft.title,'New task');assert.match(client.error,/Reference/);
 client.edit('visible','invalid json');await assert.rejects(client.save(),/JSON/);assert.equal(calls.length,2);
 client.select(seeds[0].id);assert.equal(calls.length,2);
});
test('edit/delete use stable identities, optimistic revisions and only explicit mutations',async()=>{
 let data=bank();const calls=[],client=new ChallengesClient({request:async(path,options)=>{calls.push({path,options});if(options){data={...data,revision:data.revision+1};}return data;}});
 await client.load();client.select(seeds[0].id);client.edit('title','Changed title');assert.equal(await client.save(),true);
 assert.match(calls[1].path,/\/CH-normalize-whitespace\/save$/);assert.equal(calls[1].options.body.challenge.title,'Changed title');assert.ok(!('id' in calls[1].options.body.challenge));
 await client.remove(seeds[1].id);assert.match(calls[2].path,/\/CH-stable-deduplication\/delete$/);assert.equal(calls[2].options.body.expectedRevision,2);
 assert.equal(client.data.revision,3);
});
test('bank GEPA preset freezes current bank revision with dynamic workload and no silent token increase',async()=>{
 const calls=[],client=new RuntimeClient({fetcher:async(path,options)=>{calls.push({path,options});return {ok:true,status:200,json:async()=>path==='/api/v1/llm/ollama'?{revision:7}:{}};}});
 client.data={serviceId:'bank-fixture',gepa:{revision:1,sdk:{available:true},optimizer:{available:true},versions:[],runs:[],latestRun:null},challenges:{revision:9,ready:true,counts:{train:6,validation:3,heldout:3}},provider:{config:{maxTokens:256}}};client.capabilities={csrfToken:'test-local-token'};client.enabled=true;
 client.setGepaProfile('bank');assert.equal(client.gepaMetrics,45);assert.equal(client.gepaTaskCalls,10);assert.equal(gepaPlan(client).calls,576);
 assert.match(gepaView(client.snapshot()),/至少 512/);assert.match(gepaView(client.snapshot()),/data-gepa-start[^>]*disabled/);
 client.data.provider.config.maxTokens=1024;
 assert.ok(!gepaView(client.snapshot()).match(/data-gepa-start[^>]*disabled/));
 // The production request body is captured; terminate the following refresh.
 client.refresh=async()=>{};await client.startGepa({agents:[]});
 const submitted=JSON.parse(calls.find(c=>c.path==='/api/v1/gepa/runs').options.body);
 assert.equal(submitted.profile,'bank');assert.equal(submitted.bankRevision,9);assert.equal(submitted.metricBudget,45);assert.equal(submitted.taskCallBudget,10);assert.equal(submitted.maxSeconds,7200);assert.equal(submitted.searchMode,'explore');assert.equal(submitted.proposalBudget,6);
 assert.equal(client.data.provider.config.maxTokens,1024);
});

test('exploration mode preserves pending submissions and blocks incomplete training coverage before Start',()=>{
 const client=new RuntimeClient({fetcher:()=>{throw Error('Local settings only');}});
 client.data={gepa:{sdk:{available:true},optimizer:{available:true},versions:[],runs:[]},challenges:{revision:1,ready:true,counts:{train:6,validation:3,heldout:3}},provider:{config:{maxTokens:1024}}};
 client.capabilities={};client.enabled=true;client.setGepaProfile('bank');
 const frozen={profile:'bank',searchMode:'explore',metricBudget:87};client.pendingGepaSubmission=frozen;
 assert.equal(client.gepaProposals,6);assert.equal(gepaPlan(client).verificationBatches,171);
 let html=gepaView(client.snapshot());assert.match(html,/多候選探索（建議）/);assert.match(html,/max="16"/);
 client.gepaMetrics=23;html=gepaView(client.snapshot());assert.match(html,/完整訓練覆蓋至少需要 3 個提案與 24 次搜尋評測/);assert.match(html,/data-gepa-start[^>]*disabled/);
 client.setGepaSearchMode('standard');assert.equal(client.gepaMetrics,10);assert.equal(client.gepaProposals,1);assert.equal(client.gepaSeconds,3600);
 assert.equal(client.pendingGepaSubmission,frozen);assert.equal(frozen.searchMode,'explore');
 client.setGepaSearchMode('explore');client.data.challenges.counts={train:30,validation:18,heldout:2};client.setGepaSearchMode('explore');
 assert.match(gepaView(client.snapshot()),/超過上限時請減少啟用題目/);assert.equal(client.gepaMetrics,120);
});
