import {llmView} from './llm-view.js';
import {runProgressView} from './progress-view.js';
import {OllamaUI} from './ollama-ui.js';
import {RuntimeClient} from './runtime-client.js';
import {runtimeView} from './runtime-view.js';
import {skillView,skillMarkdown} from './skill-view.js';
import {DemoAdapter} from './adapter.js';
import {BASE_SKILL,CANDIDATE_SKILL,canRelease} from './domain.js';
import {createAgentUI} from './agent-ui.js';
import {registryStats} from './agents.js';
let storage;
try { storage=window.localStorage; } catch {}
const api=new DemoAdapter(storage);
let page=['overview','agents','runtime','skills','llm','evolution','evaluations','releases','integrations'].includes(location.hash.slice(1))?location.hash.slice(1):'agents';
const labels={overview:'總覽',agents:'代理人',runtime:'執行監控',skills:'本機技能實驗',llm:'LLM 技能實驗',evolution:'演化展示',evaluations:'展示評估紀錄',releases:'展示版本管理',integrations:'框架整合'};
const live=new RuntimeClient({onUpdate(){
  const focus=document.activeElement;
  if(document.querySelector('dialog[open]')||focus?.matches('#main input, #main textarea, #main select:not([data-live-interval]):not([data-skill-limit])')){refreshProgressOnly();return;}
  if(['agents','runtime','skills','llm'].includes(page))render(true);
}});
const ollama=new OllamaUI({token:async()=>{if(!live.capabilities)await live.refresh();return live.capabilities?.csrfToken;},onUpdate(){if(page==='integrations')render();}});
const agentUI=createAgentUI({api,render,toast,runtimeSnapshot:()=>live.snapshot()});
const statusLabels={queued:'等待啟動',running:'模擬執行中',paused:'已暫停',cancelled:'已取消',completed:'已完成'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent=n=>n===null||n===undefined?'—':`${Math.round(n*100)}%`;
const date=s=>new Date(s).toLocaleString('zh-TW',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
const badge=e=>`<span class="status ${esc(e.status)}"><i></i>${statusLabels[e.status]}</span>`;
const button=(action,text,style='secondary',disabled=false)=>`<button class="button ${style}" data-action="${action}" ${disabled?'disabled':''}>${text}</button>`;
let toastTimer;
function toast(text){const el=document.querySelector('#toast');el.textContent=text;el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),4000);}
function chart(e){
 const pts=[{evaluations:0,score:e.baseline},...e.curve];
 const x=n=>48+n/e.budget*630,y=n=>170-(n-.4)/.5*135;
 const points=pts.map(p=>`${x(p.evaluations)},${y(p.score)}`).join(' ');
 return `<svg class="chart" viewBox="0 0 710 210" role="img" aria-label="模擬驗證成功率：基準 ${percent(e.baseline)}，候選 ${percent(e.candidate)}">${[.4,.6,.8].map(n=>`<line x1="48" x2="678" y1="${y(n)}" y2="${y(n)}" stroke="#e7ebf2"/><text x="4" y="${y(n)+4}">${percent(n)}</text>`).join('')}<line x1="48" x2="678" y1="${y(e.baseline)}" y2="${y(e.baseline)}" stroke="#a4afbd" stroke-dasharray="5 5"/><polygon points="48,170 ${points} ${x(e.completed)},170" fill="#edf0ff"/><polyline points="${points}" fill="none" stroke="#5b5bd6" stroke-width="3" stroke-linejoin="round"/>${pts.map(p=>`<circle cx="${x(p.evaluations)}" cy="${y(p.score)}" r="3" fill="#5b5bd6"/>`).join('')}${[0,e.budget/2,e.budget].map(n=>`<text x="${x(n)}" y="195" text-anchor="middle">${n}</text>`).join('')}<text x="355" y="209" text-anchor="middle">評估次數（模擬）</text></svg>`;
}
function metric(label,value,caption,tone=''){return `<article class="metric"><div>${label}</div><strong class="${tone}">${value}</strong><small>${caption}</small></article>`;}
function heading(title,desc,actions=''){return `<div class="page-heading"><div><p class="eyebrow">SKILL EVOLUTION · PHASE 02</p><h1>${title}</h1><p>${desc}</p></div><div class="actions">${actions}</div></div>`;}
function notice(){return `<div class="demo-banner"><span class="info-icon">i</span><div><strong>展示工作區</strong><span>實驗、曲線與測試結果皆為模擬資料。目前未連接 nanobot、GEPA 或其他代理人。</span></div><a href="#integrations">查看整合進度 ↗</a></div>${api.persistenceError?'<div class="error-banner">無法儲存至瀏覽器；目前變更僅保留於此分頁，請匯出備份。</div>':''}`;}
function experiments(state){return `<section class="card experiment-list"><div class="card-heading"><div><h2>實驗清單</h2><p>選取實驗，檢閱完整流程</p></div><span class="count">${state.experiments.length}</span></div>${state.experiments.map(e=>`<button class="experiment-item ${e.id===state.selectedId?'selected':''}" data-select="${esc(e.id)}"><div><strong>${esc(e.name)}</strong><small>${esc(e.id)} · ${date(e.createdAt)}</small></div>${badge(e)}</button>`).join('')}</section>`;}
function evolution(state,e){
 if(!e) return `${heading('技能演化','建立第一個實驗，確認技能演化與版本檢閱流程。',button('new','＋ 建立實驗','primary'))}<div class="empty card">尚無實驗。建立實驗後，可啟動展示流程。</div>`;
 const gain=e.candidate===null?null:Math.round((e.candidate-e.baseline)*100);
 let controls='';
 if(e.status==='queued')controls+=button('start','▷ 啟動展示','primary');
 if(e.status==='running')controls+=button('pause','Ⅱ 暫停');
 if(e.status==='paused')controls+=button('resume','▷ 繼續','primary');
 if(['queued','running','paused'].includes(e.status))controls+=button('cancel','取消實驗');
 const released=state.releases.some(r=>r.experimentId===e.id);
 return `${heading('技能演化','從可重現的實驗開始，讓每一次技能修改都有評估依據。',button('export','↓ 匯出紀錄')+button('new','＋ 建立實驗','primary'))}${notice()}
 <div class="metrics">${metric('基準成功率',percent(e.baseline),'驗證集 · 10 題（示例）')}${metric('候選成功率',percent(e.candidate),'相同驗證集與固定設定','accent')}${metric('相對基準改善',gain===null?'—':`${gain>=0?'+':''}${gain}<em>pp</em>`,'百分點差異 · 模擬結果',gain>0?'green':'')}${metric('已完成評估',`${e.completed}<em> / ${e.budget}</em>`,'展示流程的評估預算')}</div>
 <div class="evolution-layout"><div class="main-column"><section class="card"><div class="card-heading"><div><div class="inline-title"><h2>${esc(e.name)}</h2>${badge(e)}</div><p><code>python-fix-and-verify</code> <span>·</span> ${esc(e.id)}</p></div><div class="actions">${controls}</div></div><div class="progress-details"><span>模擬評估進度</span><strong>${Math.round(e.completed/e.budget*100)}%</strong></div><progress max="${e.budget}" value="${e.completed}" aria-label="模擬評估進度"></progress><div class="chart-title"><h3>驗證成功率</h3><div class="legend"><span><i class="candidate-dot"></i>候選</span><span><i class="baseline-dot"></i>基準</span></div></div>${chart(e)}<div class="chart-note">${e.status==='completed'?(canRelease(e)?'候選在展示情境中改善，下一步可檢閱差異並建立展示版本。':'候選沒有改善，保留基準版本；展示版本建立已停用。'):'評估僅在分頁開啟時推進；重新開啟後會暫停，等待你繼續。'}</div></section>
 <section class="card"><div class="card-heading"><div><h2>技能變更檢閱</h2><p>修改技能本文；名稱與描述在第一輪保持固定。</p></div><span class="soft-tag">SKILL.md</span></div><div class="diff"><div><div class="diff-heading">基準 · S0</div><pre>${esc(BASE_SKILL)}</pre></div><div><div class="diff-heading accent">候選 · S1 <span>${e.candidate===null?'尚未產生':'展示內容'}</span></div><pre class="candidate-code">${esc(e.candidate===null?'啟動展示後顯示候選技能。':CANDIDATE_SKILL)}</pre></div></div><div class="card-bottom"><span>${released?'此實驗已有展示版本':canRelease(e)?'已完成示例檢閱；版本切換僅影響瀏覽器展示狀態。':'候選需完成評估且改善，才能建立展示版本。'}</span>${button('release',released?'已建立展示版本':'建立展示版本 →','primary',!canRelease(e)||released)}</div></section>
 </div><div class="side-column"><section class="card"><div class="card-heading"><h2>實驗設定</h2><span class="soft-tag">固定</span></div><dl class="settings"><dt>代理人 Runtime</dt><dd>nanobot <span>規劃中</span></dd><dt>演化引擎</dt><dd>GEPA <span>規劃中</span></dd><dt>模型</dt><dd>未連接</dd><dt>資料分割</dt><dd>20 / 10 / 20 <span>示例</span></dd><dt>工作流程</dt><dd>單一 Worker</dd><dt>變更範圍</dt><dd>技能本文</dd><dt>展示情境</dt><dd>${e.scenario==='improve'?'候選改善':'沒有改善'}</dd></dl><div class="small-notice">真實後端將固定模型、工具、記憶快照與資料集版本，並隔離每次執行。</div></section><section class="card"><div class="card-heading"><h2>活動紀錄</h2><span class="live-dot"></span></div><ol class="timeline">${e.events.slice(-6).reverse().map(v=>`<li><strong>${esc(v.text)}</strong><small>${date(v.at)}</small></li>`).join('')}</ol></section>${experiments(state)}</div></div>`;
}
function evaluation(state,e){
 const done=e?.status==='completed';
 return `${heading('評估紀錄','檢閱示例資料分割、評估結果，以及沒有改善的情境。',button('export','↓ 匯出紀錄'))}${notice()}<section class="card"><div class="card-heading"><div><h2>評估概況</h2><p>目前選取：${esc(e?.name||'無實驗')}</p></div></div><div class="table-wrap"><table><thead><tr><th>資料分割</th><th>題數</th><th>用途</th><th>基準</th><th>候選</th><th>資料狀態</th></tr></thead><tbody><tr><td>Train</td><td>20</td><td>技能反思與候選產生</td><td>—</td><td>—</td><td>展示分割</td></tr><tr><td>Validation</td><td>10</td><td>候選選擇</td><td>${e?percent(e.baseline):'—'}</td><td>${e?percent(e.candidate):'—'}</td><td>模擬</td></tr><tr><td>Held-out test</td><td>20</td><td>最終檢閱示例</td><td>${done?'12 / 20':'—'}</td><td>${done?(e.scenario==='improve'?'15 / 20':'12 / 20'):'—'}</td><td>${done?'模擬，非真實驗證':'等待展示完成'}</td></tr></tbody></table></div><div class="small-notice">保留測試示例只在展示完成後顯示。真實測試集尚未建立；此頁不可作為演化改善的證據。</div></section><section class="card spaced"><div class="card-heading"><div><h2>失敗案例示例</h2><p>模擬任務，用於確認未來 trace 檢閱方式。</p></div><span class="soft-tag">SYNTHETIC</span></div><div class="table-wrap"><table><thead><tr><th>任務</th><th>觀察結果</th><th>技能修改建議</th></tr></thead><tbody><tr><td><code>demo-edge-01</code></td><td>忽略空輸入</td><td>加入邊界條件檢查</td></tr><tr><td><code>demo-regression-02</code></td><td>只執行單一測試</td><td>修復後執行完整回歸測試</td></tr><tr><td><code>demo-evidence-03</code></td><td>結論缺少命令紀錄</td><td>保留測試命令與輸出</td></tr></tbody></table></div></section>${experiments(state)}`;
}
function releases(state){return `${heading('版本管理','建立技能版本、檢閱變更與切回基準；目前僅影響本機展示狀態。',button('export','↓ 匯出紀錄'))}${notice()}<section class="card"><div class="card-heading"><div><h2>使用中的展示版本</h2><p>切換不會寫入任何代理人或 GitHub。</p></div><span class="soft-tag">${esc(state.activeReleaseId==='baseline'?'S0 · baseline':state.releases.find(r=>r.id===state.activeReleaseId)?.label)}</span></div><div class="release-row"><span class="version-icon">◇</span><div><h3>S0 · baseline</h3><p>初始技能本文 · 可隨時切回</p></div><button class="button secondary" data-activate="baseline" ${state.activeReleaseId==='baseline'?'disabled':''}>${state.activeReleaseId==='baseline'?'使用中':'切回基準'}</button></div>${state.releases.map(r=>`<div class="release-row"><span class="version-icon">↗</span><div><h3>${esc(r.label)}</h3><p>${esc(r.experimentId)} · ${date(r.createdAt)} · 展示版本</p></div><button class="button secondary" data-activate="${esc(r.id)}" ${state.activeReleaseId===r.id?'disabled':''}>${state.activeReleaseId===r.id?'使用中':'切換展示版本'}</button></div>`).join('')}${state.releases.length?'':'<div class="empty">尚未建立候選版本。前往技能演化，完成候選改善情境後檢閱。</div>'}</section>`;}
function integrations(){const rows=[['Windows Ollama','模型技能執行與反思','已實作','真實 Worker 輸出、訓練反思、版本審核'],['Local rule engine','可重現的規則技能演化','已實作','訓練回饋、實測評估、本機版本與回復'],['nanobot','第三方 Worker adapter','後續整合','Runner adapter、隔離工作區、真實 trace'],['GEPA','技能本文演化','下一階段','反思、候選產生、評估預算'],['Hermes','第二個代理人 Runtime','後續擴充','技能匯入與記憶快照'],['OpenClaw','代理人與 Gateway','後續擴充','後端 HTTP adapter、版本發布'],['Herdr','互動執行監督','後續擴充','程序狀態與 terminal 連接'],['OpenEvolve','外層工作流程演化','第二輪','固定技能後調整角色與工作順序'],['NanoClaw','隔離執行選項','後續評估','容器與執行環境整合']];return `${heading('框架整合','保留同一個 GUI，逐步換上實際執行、評估與版本服務。')}${ollama.view()}<div class="demo-banner"><span class="info-icon">i</span><div><strong>規則與模型技能流程已實作</strong><span>規則搜尋與 LLM 反思流程分開執行，皆有證據與版本審核；nanobot／GEPA SDK adapter 尚未接入。</span></div><a href="#skills">開啟本機技能實驗 ↗</a></div><section class="card"><div class="card-heading"><div><h2>整合路線圖</h2><p>本機規則引擎已可執行；第三方框架 adapter 尚未接入。</p></div><span class="soft-tag">ADAPTER FIRST</span></div><div class="table-wrap"><table><thead><tr><th>專案</th><th>角色</th><th>階段</th><th>接入範圍</th></tr></thead><tbody>${rows.map(r=>`<tr>${r.map((s,i)=>`<td>${i===0?'<strong>':''}${s}${i===0?'</strong>':''}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section><div class="two-col spaced"><section class="card"><div class="card-heading"><h2>目前已實作</h2></div><ul class="feature-list"><li>實驗建立與開始／暫停／取消</li><li>技能本文與評估曲線檢閱</li><li>展示版本建立與回復</li><li>本機規則技能演化、實測評估、版本與試跑</li><li>瀏覽器儲存、JSON 匯入／匯出</li><li>代理人角色、屬性、Skill 與工作關係設定</li><li>可獨立版本控管的程式與文件</li></ul></section><section class="card"><div class="card-heading"><h2>下一個可執行切片</h2></div><ol class="feature-list"><li>隔離的模型任務執行服務</li><li>nanobot 修復任務 Runner</li><li>可信測試與 trace 評估</li><li>GEPA 候選搜尋與保留測試</li><li>Git 技能版本與 Runtime 發布</li></ol></section></div><section class="card spaced"><div class="card-heading"><h2>資料備份</h2></div><p class="body-copy">紀錄保留於目前瀏覽器，尚未跨裝置同步。匯出 JSON 可移至另一個瀏覽器；匯入會取代本機工作區，執行中的展示實驗將轉為暫停。請勿在備份中加入 API 金鑰。</p><div class="actions card-actions">${button('export','↓ 匯出 JSON')}${button('import','↑ 匯入 JSON')}</div></section>`;}
function overview(state,e){const team=registryStats(state.registry);return `${heading('實驗總覽','技能演化的第一個可操作切片；逐步建立評估與發布流程。',button('new','＋ 建立實驗','primary'))}${notice()}<section class="card team-summary"><div><p class="eyebrow">AGENT WORKSPACE</p><h2>${team.total} 個代理人設定 · ${team.connected} 個實際連線</h2><p>${team.skills} 個 Skills · ${team.relationships} 個工作關係</p></div><button class="button secondary" data-page="agents">查看代理人 →</button></section><div class="metrics">${metric('展示實驗',state.experiments.length,'保留於目前瀏覽器')}${metric('執行中',state.experiments.filter(e=>e.status==='running').length,'僅在分頁開啟時推進')}${metric('完成實驗',state.experiments.filter(e=>e.status==='completed').length,'包含改善與沒有改善情境')}${metric('展示版本',state.releases.length,'可檢閱與切換')}</div><div class="two-col"><section class="card"><div class="card-heading"><div><h2>第一輪：技能本文演化</h2><p>固定 Runtime、模型、工具與工作流程</p></div></div><div class="phase-flow"><span class="phase-number">01</span><div><h3>建立基準</h3><p>固定設定與資料分割</p></div><span class="phase-number">02</span><div><h3>評估候選</h3><p>檢閱曲線、差異與失敗案例</p></div><span class="phase-number">03</span><div><h3>版本檢閱</h3><p>改善才建立候選版本，隨時回復</p></div></div><div class="card-actions">${button('go-evolution','開啟技能演化 →','primary')}</div></section>${experiments(state)}</div>`;}
function render(keepFocus=false){const focused=keepFocus&&document.activeElement?.closest('#main button, #main [data-live-interval], #main [data-skill-limit]');const focusData=focused?{...focused.dataset}:null;const s=api.snapshot(),e=s.experiments.find(v=>v.id===s.selectedId);document.querySelector('#breadcrumb').textContent=labels[page];document.querySelector('.mode-pill').textContent=['runtime','skills','llm'].includes(page)?'本機實際執行':'配置／展示模式';document.querySelector('#agent-nav-count').textContent=s.registry.agents.length;document.querySelectorAll('[data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page===page);b.setAttribute('aria-current',b.dataset.page===page?'page':'false');});document.querySelector('#main').innerHTML=page==='llm'?llmView(live.snapshot()):page==='skills'?skillView(live.snapshot()):page==='runtime'?runtimeView(live.snapshot()):page==='agents'?agentUI.view(s)+(api.persistenceError?'<div class="error-banner spaced">無法儲存至瀏覽器；請匯出工作區備份。</div>':''):page==='evolution'?evolution(s,e):page==='evaluations'?evaluation(s,e):page==='releases'?releases(s):page==='integrations'?integrations():overview(s,e);if(focusData){const next=[...document.querySelectorAll('#main button, #main [data-live-interval], #main [data-skill-limit]')].find(b=>Object.entries(focusData).every(([k,v])=>b.dataset[k]===v));next?.focus({preventScroll:true});}}
function refreshProgressOnly(){
 const target=document.querySelector('[data-execution-progress]');
 if(!target||!['llm','skills','runtime'].includes(page))return;
 const state=live.snapshot();
 const run=page==='llm'?(state.selectedLlmRun||state.data?.llm?.latestRun):page==='skills'?(state.selectedSkillRun||state.data?.skills?.latestRun):state.data?.latestRun;
 target.outerHTML=runProgressView(state,run);
}
function navigate(next){page=next;history.replaceState(null,'',`#${next}`);render();if(next==='integrations')ollama.operate('reload').catch(()=>{});}
document.addEventListener('click',async event=>{
 const b=event.target.closest('button');if(!b)return;
 // Let the browser dispatch submit before any rendering can detach the form.
 if(b.form&&b.type==='submit')return;
 try{
 if(b.dataset.page) return navigate(b.dataset.page);
 if(b.dataset.ollama){await ollama.operate(b.dataset.ollama);return;}
 if(b.hasAttribute('data-llm-start')){await live.startLlm(api.snapshot().registry);toast('已提交真實模型技能演化；只依已儲存模型設定執行');return;}
 if(b.dataset.llmApprove){await live.approveLlm(b.dataset.llmApprove);toast('已核准並啟用模型技能版本');return;}
 if(b.dataset.llmActivate){await live.activateLlm(b.dataset.llmActivate);toast('已切換模型技能版本');return;}
 if(b.hasAttribute('data-llm-select')){await live.selectLlmRun(b.dataset.llmSelect);return;}
 if(b.dataset.llmExport){const v=live.data?.llm?.versions.find(v=>v.id===b.dataset.llmExport);if(!v)throw Error('版本尚未載入');const url=URL.createObjectURL(new Blob([skillMarkdown(v)],{type:'text/markdown;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`${v.skill.name}-${v.label}-SKILL.md`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
 if(b.hasAttribute('data-live-refresh')){await live.refresh();return;}
 if(b.hasAttribute('data-live-run')){await live.run(api.snapshot().registry);toast('已提交實際專案檢查工作');return;}
 if(b.dataset.liveCancel){await live.cancel(b.dataset.liveCancel);toast('已請求取消；程序狀態由 polling 確認');return;}
 if(b.hasAttribute('data-live-toggle')){if(live.enabled)live.stop();else await live.start();return;}
 if(b.hasAttribute('data-skill-start')){await live.startSkill(api.snapshot().registry);toast('已提交本機技能演化；每個候選都會實際評估');return;}
 if(b.dataset.skillApprove){await live.approveSkill(b.dataset.skillApprove);toast('已核准並啟用本機技能版本；後續實驗使用新基準');return;}
 if(b.dataset.skillActivate){await live.activateSkill(b.dataset.skillActivate);toast('已切換本機技能版本；執行中的工作保留原設定');return;}
 if(b.hasAttribute('data-skill-select')){await live.selectSkillRun(b.dataset.skillSelect);return;}
 if(b.dataset.skillExport){const version=live.data?.skills?.versions.find(v=>v.id===b.dataset.skillExport);if(!version)throw Error('技能版本尚未載入');const blob=new Blob([skillMarkdown(version)],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`${version.skill.name}-${version.label}-SKILL.md`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
 if(agentUI.handleClick(b))return;
 if(b.hasAttribute('data-close'))return b.closest('dialog')?.close();
 if(b.dataset.select){api.select(b.dataset.select);navigate('evolution');return;}
 if(b.dataset.activate){api.activate(b.dataset.activate);render();toast('已切換本機展示版本');return;}
 const a=b.dataset.action;
 if(a==='new') return document.querySelector('dialog').showModal();
 if(a==='export'){const blob=new Blob([JSON.stringify(api.snapshot(),null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='nanobot-gepa-workspace.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已匯出工作區，包含代理人與工作關係');return;}
 if(a==='import')return document.querySelector('#import-file').click();
 if(a==='go-evolution')return navigate('evolution');
 if(a==='release'){api.release();toast('已建立展示版本；尚未部署到 Runtime');}
 else if(['start','pause','resume','cancel'].includes(a))api.action(a);
 if(a==='release'||['start','pause','resume','cancel'].includes(a))render();
 }catch(error){toast(error.message);}
});
document.querySelector('#experiment-form').addEventListener('submit',event=>{event.preventDefault();try{const fields=new FormData(event.target);api.create({name:fields.get('name'),budget:Number(fields.get('budget')),scenario:fields.get('scenario')});document.querySelector('dialog').close();navigate('evolution');toast('已建立實驗，按「啟動展示」開始');}catch(error){toast(error.message);}});
document.addEventListener('submit',async event=>{if(event.target.id==='ollama-settings-form'||event.target.id==='ollama-chat-form'){event.preventDefault();const fields=new FormData(event.target);try{if(event.target.id==='ollama-settings-form'){const config={};for(const [key,value] of fields)config[key]=['host','model'].includes(key)?value:Number(value);await ollama.operate('save',config);toast('已儲存 Ollama 設定；沒有發出連線測試');}else{ollama.prompt=fields.get('prompt');await ollama.operate('chat');toast('單次模型請求已完成');}}catch(error){toast(error.message);}return;}if(event.target.id!=='skill-trial-form')return;event.preventDefault();try{await live.trySkill(new FormData(event.target).get('text'));render();toast('已使用本機啟用版本試跑');}catch(error){toast(error.message);}});
document.addEventListener('input',event=>{if(event.target.matches('#ollama-settings-form input'))ollama.edit(event.target.name,event.target.value);if(event.target.matches('#ollama-chat-form textarea'))ollama.prompt=event.target.value;if(event.target.matches('[data-skill-input]'))live.trialInput=event.target.value;});
document.querySelector('#import-file').addEventListener('change',async event=>{const file=event.target.files[0];try{if(!file)return;if(file.size>2000000)throw Error('資料檔案上限為 2 MB');const data=JSON.parse(await file.text());if(!window.confirm('匯入會取代目前瀏覽器的實驗、代理人與工作關係設定，是否繼續？'))return;api.import(data);render();toast('已匯入工作區；執行中的展示實驗已暫停');}catch(error){toast(`匯入失敗：${error.message}`);}finally{event.target.value='';}});
document.addEventListener('change',event=>{if(event.target.matches('[data-llm-call-seconds]'))live.llmCallSeconds=Number(event.target.value);if(event.target.matches('[data-llm-profile]'))live.llmProfile=event.target.value;if(event.target.matches('[data-llm-seconds]'))live.llmSeconds=Number(event.target.value);if(event.target.matches('[data-live-interval]'))live.setInterval(event.target.value);if(event.target.matches('[data-skill-limit]')){live.skillLimit=Number(event.target.value);render(true);}});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(labels[next]){page=next;render();if(next==='integrations')ollama.operate('reload').catch(()=>{});}});
setInterval(()=>{try{if(api.tick()&&!['agents','runtime','skills','llm','integrations'].includes(page))render(true);}catch(error){toast(error.message);}},1200);
render();
live.start();
if(page==='integrations')ollama.operate('reload').catch(()=>{});
window.addEventListener('pagehide',()=>live.stop());
window.addEventListener('pageshow',event=>{if(event.persisted)live.start();});
if(api.recoveryWarning)toast('原有本機資料無法讀取，已載入初始示例；請從備份重新匯入。');
