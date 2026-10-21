# Paired final comparison (逐題成效比較)

New GEPA experiments freeze `comparisonPolicy=paired-zero-regression-v1` before dispatch. The GUI lists each validation and held-out task's independent baseline and selected result, identifies both rollout IDs, and separates improved, regressed, retained pass and retained failure (改善、退步、持續通過、仍未通過). Bank difficulty, topic and group come from the frozen dataset, never today's editor.

## Release behavior (發布條件)

All existing gates remain, with a stricter per-task condition for new experiments:

1. The selected Skill body must differ from the baseline.
2. Independent validation must improve in total successful tasks.
3. The held-out total must not decrease.
4. Neither validation nor held-out may lose any baseline success.
5. Independent evidence replay, current baseline identity and explicit operator approval remain mandatory.

A baseline score of 1/3 and selected score of 2/3 can contain two gains and one loss. The previous aggregate rule could accept that result. New experiments finish evaluation and retain the candidate, but refuse release with `validation-task-regressed` and/or `heldout-task-regressed`. The optimizer still selects using search validation only. A rejected selected candidate does not trigger another selection using final results.

Comparison is constructed only after every rollout passes the existing evidence checks. Duplicate/missing final task identities, invalid scores or mismatched stored tests remain fatal. Evaluator and reviewer independently reconstruct the comparison; approval replays again. Removing or changing the frozen policy fails its provenance check. New result fields are `comparison` and `releaseBlockers` in the saved evaluation/review/Run result.

Historical saved Runs and approved versions are not rewritten. Results without a frozen comparison policy retain their saved aggregate verdict; the GUI reports the absence of paired evidence. Updating source continues to invalidate approval replay of older source under the existing provenance contract. An upgrade does not make an old result newly approvable.

## Reading results (成果判讀)

Open **GEPA 技能最佳化 → 實際演化成果 → 逐題比較**. The table is always visible for a completed, reviewed new experiment; polling cannot close it. Running, interrupted, cancelled or failed experiments do not display provisional pairs as confirmed final results. Selecting an older Run uses its own saved evidence and policy.

A retained pass has no upward headroom under the binary whole-task score. A retained failure identifies an unsolved task in this comparison. Neither category proves that the bank is universally too easy or too hard. V3 difficulty remains an authored estimate. Repeated experiments with frozen provider/model, Skill, dataset revision and budgets are needed to measure model variability; this delivery adds no significance or causal generalization claim.

Keep held-out results outside reflection. Use training feedback and search validation to improve the method; preserve a frozen independent set for transfer evaluation. Do not tune each new Skill against reported held-out failures and call it unseen evidence.

## Work and verification boundaries (工作量與驗證範圍)

Comparison is an in-memory projection of already verified final rows. It adds zero model requests, zero task rollouts and zero trusted-test subprocesses. GUI reads render saved results without SDK imports or recomputing scores. Existing deadlines, output/call limits, training feedback and summary completion policy remain unchanged. This increment does not implement interrupted GEPA optimizer resume or complete phase M.

The negative SDK case is `paired_workflow_test.PairedWorkflowTests.test_net_gain_with_lost_passes_completes_review_but_cannot_release`. Its graph is test runner → RuntimeService → coordinator → pinned GEPA worker → fresh nanobot processes → visible tools plus immediate verification → independent final tasks → evaluator replay → reviewer replay → refused approval. A forged saved eligibility flag additionally exercises independent approval replay and is rejected. The shipped JavaScript parser and GUI consume the actual result.

This case and the existing V3 positive case each reserve at most 22 rollouts, 133 model requests and 66 workflow verifier batches: 120 seconds startup + 133×10 seconds requests + 22×(24×5 seconds tool allowance + 3×5 seconds trusted batches) + 30 seconds cleanup = 4450 workflow seconds. Terminal collection adds 30 seconds; one extra approval replay reserves 110 seconds and a JS consumer reserves ten seconds. V3 import may add up to 300 seconds. Each case has its own module process bounded by the existing 7200-second supervisor; these ceilings are not combined under a shorter parent.

Smoke controls use the existing `gepa_validation_budget.py` graph, including three verification passes and separately counted approval/tamper replays. The release wildcard discovers the two new Python modules (`gepa_comparison_test.py`, `paired_workflow_test.py`); the manifest invariant includes both and preserves exact-case splitting of the existing GEPA module. No supervisor cap is increased.

Scripted loopback responses establish implementation behavior, not a new Strata/Ollama gain, Windows/GPU stability, Docker isolation or full M acceptance.

## Scoped verification results (本次驗證結果)

The frozen source passed 30 distinct Python cases and all 146 frontend cases with zero skips. Python scope comprises four comparison contracts, eight workload/manifest cases, twelve exploration cases and six actual SDK cases: net-gain regression, V3 improvement/approval, Smoke improvement/approval/rollback/tamper rejection, perfect seed, held-out regression and verified task-cap continuation. Ruff on changed Python, source credential-pattern scanning and whitespace checks also pass. Exact reports and the source manifest are retained under `.local/test-reports/paired-comparison/`; frontend output is `.local/test-reports/paired-frontend.log`.

| Actual SDK evidence (實際執行紀錄) | Rollouts | Requests | Three workflow passes | After approval replay |
| --- | ---: | ---: | ---: | ---: |
| Net gain with lost passes; refused release | 22 | 56 | 66 batches | 88 batches after forged-flag rejection |
| V3 improvement; approved | 22 | 56 | 66 batches | 88 batches |
| Smoke improvement; approved, rolled back and tamper rejected | 18 | 46 | 54 batches | 126 batches after four extra replay passes |
| Perfect seed; no new candidate or release | 17 | 68 | 51 batches | No approval replay |
| Task-cap continuation; seven failed tasks retain zero scores | 22 | 79 | 66 batches | Existing approval/tamper assertions retained |

The first negative integration attempt on the default temporary directory failed during evaluator replay at R0011: the saved candidate was repaired, while the workspace source and tool journal no longer matched the completed immediate-verification evidence. The strict verifier rejected it. Original evidence is retained at `.local/test-reports/challenge-workflow/382724ca4dd74cdda1ed0011d4fd9e31`, Run `RUN-e6a720bc-de84-4921-9556-a915c90bbeb0`; this is not a successful comparison. The exact case passed on unchanged source using an independent temporary root inside the checkout (`TMPDIR=$PWD/.local/validation-tmp`), followed by the unexecuted tail under that same root. The cause of the original artifact inconsistency remains unestablished; this delivery does not claim to fix filesystem durability or qualify the default temporary directory.
