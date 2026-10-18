// Work counts, not a prediction that the configured wall-clock cap will suffice.
export const GEPA_PRESETS={smoke:{metrics:8,proposals:2,seconds:1800},full:{metrics:26,proposals:1,seconds:7200},bank:{metrics:87,proposals:12,seconds:7200}};
export function explorationPlan(runtime){
 const counts=runtime.data?.challenges?.counts??{train:6,validation:3},batches=Math.ceil(counts.train/2);
 const minimum=counts.validation+batches*(4+counts.validation);
 return {minimum,batches,planned:counts.validation+Number(runtime.gepaProposals??12)*(4+counts.validation)};
}
export function gepaPlan(runtime){
 const full=runtime.gepaProfile==='full',bank=runtime.gepaProfile==='bank',counts=runtime.data?.challenges?.counts;
 const validation=bank?(counts?.validation??3):full?10:2,heldout=bank?(counts?.heldout??3):full?20:4;
 const search=Number(runtime.gepaMetrics??GEPA_PRESETS[bank?'bank':full?'full':'smoke'].metrics);
 const final=2*(validation+heldout),rollouts=search+final;
 const calls=rollouts*Number(runtime.gepaTaskCalls??8)+Number(runtime.gepaProposals??GEPA_PRESETS[bank?'bank':full?'full':'smoke'].proposals);
 return {search,final,rollouts,calls,verificationBatches:3*rollouts,
  seconds:Number(runtime.gepaSeconds??GEPA_PRESETS[bank?'bank':full?'full':'smoke'].seconds),full};
}

export function gepaPlanView(runtime){
 const plan=gepaPlan(runtime);
 const explore=runtime.gepaProfile==='bank'&&runtime.gepaSearchMode!=='standard',e=explorationPlan(runtime);
 return `<div class="small-notice" data-gepa-plan><strong>提交前工作量（上限）</strong>：搜尋 ${plan.search} 次 + 基準／候選最後評測 ${plan.final} 次 = ${plan.rollouts} 次 rollout；模型最多 ${plan.calls} 次；可信驗證共 ${plan.verificationBatches} 批（即時驗證、評估重播、審查重播各一次）。<br>切換規模會套用搜尋與時間預設，可再手動調整。Smoke／Full 預設也使用探索，滿分批次仍可產生候選。Full 預設搜尋 26、提案 1、整輪 7200 秒；Smoke 探索為 10、2、1800 秒；標準模式為 8、2、1800 秒。${plan.full&&plan.seconds<7200?'<br><strong>目前 Full 的時間低於 7200 秒預設；僅最後評測就有 60 次 rollout，容易在取得最終成果前逾時。</strong>':''}<br>時間為使用者設定的硬上限，沒有自動延長或重試；7200 秒不保證任意模型／主機都能完成。搜尋進度不包含後續獨立評測。${runtime.gepaProfile==='bank'?`<br>多難度題庫預設多候選探索、提案 12、每題 10 次呼叫、整輪 7200 秒；搜尋量依目前啟用題目計算。輸出上限至少 512 tokens，建議先在框架整合儲存 1024。${explore?`<br>完整訓練覆蓋至少需要 ${e.batches} 個提案額度與 ${e.minimum} 次搜尋評測；目前提案上限全部進入驗證時需 ${e.planned} 次。${plan.search<e.planned?'<strong>目前搜尋額度可能先於提案額度耗盡。</strong>':''}候選可能重複、退步或未完成；提案上限不保證不同 Skill 數量。`:''}`:''}</div>`;
}
