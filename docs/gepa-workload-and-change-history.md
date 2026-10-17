# Workload and Change History (工作量與修改歷程)

This update separates three forms of evidence: a Python source edit, a changed Skill prompt, and an independently measured improvement (程式修復、Skill 修改、實測改善). It adds read-only inspection and corrects the GUI profile presets. It does not change the benchmark, score policy, SDK, release gates, or already frozen runs.

## Timeout finding (逾時原因)

The supplied diagnostics identify a Full GEPA workflow with an 1,800-second wall-clock limit, 80 search evaluations, four proposal slots, eight calls per task, and 1,124 global call slots. The workflow was stopped during search after 37 completed rollouts and 193 completed model calls. The next rollout had a successful visible-test tool result shortly before termination. Final baseline/selected evaluation and independent reviewer replay had not completed.

The model and tools were still making progress. This is an exhausted whole-workflow budget, not evidence of a network failure, a failed Python repair, or model inability. The GUI changed the workload when selecting Full but retained Smoke's 30-minute limit. A call limit is a capacity ceiling, not a reservation of enough wall-clock time to consume it.

The separate uploaded repair archive is an older single-repair record. It contains a real source change and successful independent evaluation; it is not the failed Full GEPA artifact directory. Diagnostic metadata supports the timeout boundary and work counts, but cannot establish every proposal body or the unfinished rollout's complete source history. The new history endpoint reads those original artifacts on the operator's checkout without another experiment.

## Corrected presets and explicit counts (預設與工作量)

| GUI preset | Search ceiling | Required final rollouts | Total rollout ceiling | Calls/task | Proposals | Global call ceiling | Whole-run cap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke | 8 | 12 | 20 | 8 | 2 | 162 | 1,800 s |
| Full, initial bounded search | 26 | 60 | 86 | 8 | 1 | 689 | 7,200 s |
| Previous Full preset | 80 | 60 | 140 | 8 | 4 | 1,124 | 1,800 s |

The required final count evaluates baseline and selected Skills separately on every validation and held-out task: twice the sum of the two split sizes. Search alone is therefore not the whole workload. Each rollout also requires immediate trusted verification, evaluator replay and independent reviewer replay: up to 60 batches for Smoke or 258 for the new Full preset, in addition to visible-test tools. Final evaluation and replay remain mandatory even when the same Skill is selected.

The page shows these counts before submission. Selecting a profile applies its displayed presets; users can then adjust them. An explicit shorter Full limit produces a visible warning. Rendering, polling and history inspection never extend it. Existing frozen requests, uncertain submissions, cancellation, per-call timeouts and historical failures retain their original limits. No automatic retry or resume is added.

The new Full preset reduces search from 80 to the minimum 26 evaluations that can contain initial validation plus a complete parent/child reflection iteration and validation. It also changes the proposed wall-clock cap to two hours. These are operating defaults, not a proof that any model or WSL filesystem will finish in that time. The observed approximately 49 seconds per completed search rollout already implies roughly 49 minutes for 60 final rollouts alone if that pace continued, before other phases. Extrapolation is planning evidence, not a new completed Full result.

## Inspect actual changes (檢閱實際修改)

Open either **Python 修復實驗** or **GEPA 技能最佳化**, select the intended Run, and click **顯示實際修改歷程**. Failed, cancelled, interrupted and running records are inspectable. The button reads saved files only. Refresh the history explicitly to inspect later steps of a running experiment.

- GEPA lists 20 rollouts per page, including an unfinished rollout directory that is absent from the completed ledger. Choose a rollout to inspect its frozen task requirements, initial source, granted tool steps, current source and the Skill actually used.
- Every successful `write_solution` shows its before/after source and unified diff. Writing the same source is labeled unchanged. A rejected write shows the attempted source separately and leaves the reconstructed current source unchanged.
- Reads and tests explicitly say the program did not change. Test steps show the saved visible passed/total counts; those local counts are not promoted to an independent final result.
- Skill history includes the frozen baseline, each saved proposal, an unchanged proposal when the model returns the same body, and the final selection or an explicit pending state. Changed proposals show before/after text and a diff. Search validation scores, nonselection and selection remain distinct from release eligibility and activation.
- Single Python repair uses a fixed Skill throughout. Its source change is not a Skill evolution. GEPA's repeated rollouts can likewise reuse the baseline without producing a proposal. The viewer never fabricates an unrecorded optimizer attempt or a reason for an unrecorded decision.

Open details are preserved through ordinary status polling. Switching Runs does not display another Run's history; stale asynchronous replies cannot replace a newer selection. Missing, oversized or partial files produce unknown fields or warnings, not invented code or success. A frozen candidate is checked against the reconstructed sequence for display only; independent scoring is never recomputed in this read path.

`GET /api/v1/debug/changes/RUN-…` uses the existing localhost/origin boundary. Optional parameters are `rollout=R0001`, `offset=0`, and `limit=20`. Reads are bounded by file, aggregate bytes, rollout count and tool count. Symlinks and nonregular files are rejected. The response projects task source, selected Skill bodies and visible counts only; provider credentials, raw model request/response bodies and hidden-test contents are excluded. Task source is intentionally visible to the local operator and remains excluded from the diagnostic ZIP.

## Benchmark limitations and next dataset design (題庫限制與下一版設計)

Current Smoke has 4/2/4 tasks; Full has 20/10/20. Both use ten disjoint operation families. Full adds five offsets per family, but every task starts from the same `return value` stub and the task contract often states the required formula directly. More offsets increase work and sample count without establishing broad software-repair difficulty. A perfect seed can legitimately produce no proposal or improvement.

The next dataset should use a **new dataset version**, independently audited tests, distinct erroneous starting programs, and difficulty calibrated by actual baseline outcomes. Suggested categories are:

| Defect category | Starting-program design | What a transferable Skill must help with |
| --- | --- | --- |
| Boundary and comparison | Nearly correct implementation with an inclusive/exclusive boundary error | Check equality and boundary inputs, not only ordinary examples |
| Branch ordering and exceptions | Early return suppresses a required invalid-input exception | Inspect preconditions and control-flow order |
| Sign and arithmetic | Positive examples pass but negative or equal-bound cases fail | Identify invariants and test complementary cases |
| Multiple interacting defects | A partial repair fixes one case and exposes another | Use failure evidence to make a second justified correction |
| Visible-only overfit | An implementation matches public cases but violates the general contract | Derive behavior from the requirement rather than memorizing examples |
| Broader Python behavior | Collections, state, parsing, imports or multiple files | Requires a separately designed sandbox and evaluator; unsupported syntax cannot simply be enabled in the current bounded runner |

These categories originally described the next dataset design. The follow-up now ships a separate [versioned 12-question challenge bank and editor](python-challenge-bank.md), with a new opt-in pure-Python policy; Smoke/Full and old evidence remain separate. "Harder" must not mean an ambiguous, impossible, unsupported or incorrectly scored problem. Include easy control cases and harder cases with meaningful headroom; do not alter held-out tasks to force a desired improvement.

Group near-duplicate programs, algorithm families and shared bug templates before assigning train/validation/test splits. Only training trajectories enter reflection; validation selects candidates; a frozen unseen test set measures transfer. Use the same model, tools, task budgets and dataset revision for baseline/selected comparisons. Report success by defect family and difficulty, visible-to-hidden regressions, call/token cost and repeated-run variability. A single improved prompt or larger aggregate sample is not proof of broad agent evolution. GEPA evolves instructions; model weights remain fixed.

Primary references: [GEPA paper](https://arxiv.org/abs/2507.19457), [official GEPA FAQ on validation/test separation and overfitting](https://github.com/gepa-ai/gepa/blob/main/docs/docs/guides/faq.md), and [SWE-bench's task-and-patch evaluation](https://github.com/SWE-bench/SWE-bench). These motivate evaluation design; this project does not claim their benchmark performance.

## Maintenance rule and verification (維護規則與驗證)

When a profile or mandatory phase changes, audit the actual form defaults and submitted payload, named work counts, final evaluation and all replay passes. A passing Smoke run does not qualify Full's operating budget. Count ceilings separately from runtime estimates and enforced deadlines. Keep immutable execution evidence and a scoped validation record instead of asking an operator to repeat a long run just to reveal the next missing phase.

Local validation passed 8 no-model Python history/API cases and 43 focused frontend cases, with zero skips. Ruff on the changed Python files, the source credential-pattern scan and diff checks also passed. The regression scope covers for failed attempts, unchanged writes/proposals, incomplete rollouts, pagination, origin/path/file bounds, stale responses, open-detail preservation and real profile submission. The uploaded older repair was also projected through the actual reader and frontend validator: its one source edit, visible 6/6 result and fixed Skill appear without executing the uploaded code. No new Windows/GPU experiment, complete Full run, broad M7 rerun or browser visual qualification is claimed.

## Per-question attempt records (逐題修復與 Skill 對照紀錄)

The GEPA page now loads its saved attempt table immediately below **實際演化成果**. Each row identifies the rollout, question, frozen difficulty/topic/split, search or independent-final phase, same-question attempt ordinal, actual Skill name/hash and baseline/proposal identity. It shows the saved independent public/retained passed/total counts for both the faulty starting program and final candidate, plus model-call count. Source-write requests, applied writes, effective changes and rejected writes have separate counters. A rollout always starts fresh; the same-question ordinal across phases does not imply continuing the previous candidate's program. Tool details below the table still show every accepted, unchanged or rejected edit and its actual code.

The ordinal is calculated across the complete bounded rollout list before pagination, so page two does not reset it. A bank coverage table lists every frozen question, including **未執行・沒有測量結果**. Search can sample only part of training; coverage is not a claim that every question received a rollout. Unknown task identities make later ordinals unknown rather than silently undercounting. Difficulty/title/topic come only from the run's immutable dataset snapshot. Editing or deleting today's catalog cannot relabel an earlier experiment. Legacy runs without that snapshot retain task IDs, attempts and saved results without invented question metadata.

Counts are a projection of `repair-evaluation.json`, not a new evaluation. The saved task identity, completion ledger, evidence identity and task score must agree before projecting independent counts. Missing, partial, oversized or inconsistent evidence produces unavailable fields or warnings; it is never a zero or a perfect result. A task-cap outcome retains its failed result and `max_iterations`, even if its last source passes all cases. Aggregate review and per-task results remain separate. The projection strips evaluator details, retained inputs/answers, credentials and raw model bodies. It never imports an optional SDK, executes source, writes artifacts or dispatches a model.

Automatic reads occur on GEPA navigation or a changed run/status/completed-rollout count. Unchanged polls add no history requests; reads coalesce and failed reads require explicit refresh or a later state change. Each request still contains at most 20 rollout rows and reads at most 8 MiB in total. When the byte ceiling is reached, later previews are omitted with bounded warnings. Open source/Skill details retain the displayed snapshot even if an automatic read finishes after the user expands one. Closing details allows a later poll to display the newer snapshot; explicit history refresh, rollout selection or pagination updates immediately.

A completed experiment need not discover a better Skill. The current metric is binary task success, not the number of source edits, calls saved or speed. A seed at 100% has no higher success score available. The configured GEPA `skip_perfect_score=True` also skips mutation when every sampled training score is perfect; the iteration-reservation stop guard may then end a bounded search before all training questions are sampled. A proposed Skill is still subject to validation selection and independent held-out evaluation. Do not force proposals, change historical results or weaken release gates to make evolution appear successful. Use separate revisioned training/validation design and repeated baseline measurements to calibrate meaningful headroom; author-assigned hard labels alone do not establish it.

Focused verification: 12 read-only Python/API cases and 57 frontend cases passed. The real pinned SDK integration with scripted loopback model replies also passed search, repair, final evaluation, evaluator/reviewer, approval and tamper rejection; its actual saved attempt pages passed the shipped JavaScript parser and renderer. The integration checks that reading adds no model calls, reflects independent saved counts exactly, and retains the frozen question titles after a live-bank edit. No new Windows/GPU performance or broader M7 acceptance is claimed.

See [Skill generation history](skill-generation-history.md) for retained candidates, generation conditions, cross-Run queries and the explicit diagnostic Skill-artifact section.
