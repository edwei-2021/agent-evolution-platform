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
 client.setGepaProfile('bank');assert.equal(client.gepaMetrics,10);assert.equal(client.gepaTaskCalls,10);assert.equal(gepaPlan(client).calls,221);
 assert.match(gepaView(client.snapshot()),/至少 512/);assert.match(gepaView(client.snapshot()),/data-gepa-start[^>]*disabled/);
 client.data.provider.config.maxTokens=1024;
 assert.ok(!gepaView(client.snapshot()).match(/data-gepa-start[^>]*disabled/));
 // The production request body is captured; terminate the following refresh.
 client.refresh=async()=>{};await client.startGepa({agents:[]});
 const submitted=JSON.parse(calls.find(c=>c.path==='/api/v1/gepa/runs').options.body);
 assert.equal(submitted.profile,'bank');assert.equal(submitted.bankRevision,9);assert.equal(submitted.metricBudget,10);assert.equal(submitted.taskCallBudget,10);assert.equal(submitted.maxSeconds,3600);
 assert.equal(client.data.provider.config.maxTokens,1024);
});
