import test from 'node:test';
import assert from 'node:assert/strict';
import {MatrixClient} from '../dist/js/matrix-client.js';
import {matrixView} from '../dist/js/matrix-view.js';

test('Web matrix client starts only the complete plan, polls and exposes the archive',async()=>{
  const calls=[],id='MAT-'+'a'.repeat(32);
  const job={id,status:'completed',archiveReady:true,createdAt:'2026-10-23T00:00:00Z',
    summary:{status:'passed',coverage:{flowPasses:{configurations:3,components:3,acceptance:3},
      ratePercent:100,coveredPaths:103,totalPaths:103,minimumRatePercent:60,
      modelQuestionRatePercent:100,modelQuestionsCovered:60,modelQuestionsTotal:60,missingPaths:[]},
      attempts:[{flow:'acceptance',round:3,status:'passed',exitCode:0}]}};
  const client=new MatrixClient({request:async(path,options)=>{
    calls.push({path,options});
    return options?.method==='POST'?{...job,status:'queued'}:path.endsWith(id)?job:{jobs:[job]};
  }});
  await client.start();
  assert.deepEqual(calls[0],{path:'/api/v1/tests/matrix',options:{method:'POST',body:{}}});
  assert.match(matrixView(client),/下載測試紀錄 ZIP/);
  assert.match(matrixView(client),/驗收 3\/3/);
  assert.match(matrixView(client),/103\/103/);
  assert.match(matrixView(client),/最低 60%/);
  await client.cancel();
  assert.ok(calls.some(call=>call.path===`/api/v1/tests/matrix/${id}/cancel`&&call.options?.method==='POST'));
});

test('Worker output is escaped before display',()=>{
  const view=matrixView({selected:{id:'MAT-'+'b'.repeat(32),status:'failed',logTail:'<script>alert(1)</script>',
    error:'<bad>',summary:{attempts:[],coverage:{workflowPasses:{'<route>':0},missingPaths:['<missing>']}}},jobs:[],busy:false,error:null});
  assert.doesNotMatch(view,/<script>|<bad>/);
  assert.match(view,/&lt;script&gt;/);
  assert.doesNotMatch(view,/<missing>|<route>/);
});
