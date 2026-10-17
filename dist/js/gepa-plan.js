// Work counts, not a prediction that the configured wall-clock cap will suffice.
export const GEPA_PRESETS={smoke:{metrics:8,proposals:2,seconds:1800},full:{metrics:26,proposals:1,seconds:7200},bank:{metrics:10,proposals:1,seconds:3600}};
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
 return `<div class="small-notice" data-gepa-plan><strong>提交前工作量（上限）</strong>：搜尋 ${plan.search} 次 + 基準／候選最後評測 ${plan.final} 次 = ${plan.rollouts} 次 rollout；模型最多 ${plan.calls} 次；可信驗證共 ${plan.verificationBatches} 批（即時驗證、評估重播、審查重播各一次）。<br>切換規模會套用搜尋與時間預設，可再手動調整。Full 預設搜尋 26、提案 1、整輪 7200 秒；Smoke 為 8、2、1800 秒。${plan.full&&plan.seconds<7200?'<br><strong>目前 Full 的時間低於 7200 秒預設；僅最後評測就有 60 次 rollout，容易在取得最終成果前逾時。</strong>':''}<br>時間為使用者設定的硬上限，沒有自動延長或重試；7200 秒不保證任意模型／主機都能完成。搜尋進度不包含後續獨立評測。${runtime.gepaProfile==='bank'?'<br>多難度題庫預設搜尋 10、提案 1、每題 10 次呼叫、整輪 3600 秒；分割與呼叫量依目前啟用題目計算。輸出上限至少 512 tokens，建議先在框架整合儲存 1024。':''}</div>`;
}
