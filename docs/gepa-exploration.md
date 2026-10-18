# Multi-candidate GEPA exploration (多候選探索)

The GUI now defaults to exploration for Smoke, Full and the challenge bank. New exploration configurations freeze `failure-diversity-v2`; API calls omitting `searchMode` retain standard behavior. Smoke/Full remain synthetic flow checks, and the challenge bank is the recommended evolution experiment. The former standard configuration could consume three validation tasks and two perfect training tasks, skip reflection, then stop because the remaining five metric slots could not reserve a seven-evaluation iteration. Retention alone did not fix that search limitation.

## Search behavior (搜尋行為)

Exploration uses the pinned GEPA 0.1.4 optimizer and the same nanobot 0.3.5 repair runner. It changes candidate search, while preserving the binary trusted task score and independent release gates.

- A queue samples every training task before beginning a new shuffled epoch. A short final batch is allowed. A server-generated seed is frozen per Run and retained for replay; it does not change model temperature or weights.
- Perfect training batches may propose instructions. Sixteen explicit, general repair strategies rotate across attempts: contract, boundaries, permitted syntax, invariants, minimal repair, budgeting, input preservation, recovery, generalization, control flow, test interpretation, concise workflow, representation, stable order, multistep repair and synthesis.
- Reflection receives the parent, actual training trajectories, up to three distinct preceding instructions, and a compact memory of up to four failed training tasks. The memory retains rejection categories and aggregate training-test counts, not test inputs/answers. Four explicit mutation operations (rewrite, replace, reorder and compress) rotate alongside the sixteen strategies. No validation or held-out trajectories enter reflection. The existing system prompt still prohibits solution code and task-specific answers.
- A distinct candidate whose training score equals its parent's score may proceed to full search validation. A training regression is rejected. Before child evaluation, whitespace-normalized instruction identity is compared with the baseline and **all** preceding generated bodies, including rejected bodies. A duplicate is archived and returns GEPA's native empty-update result: no child rollout and no invented/cached score.
- Only reflection uses temperature 0.7, rising to 1.0 after two consecutive duplicates. Repair and final evaluation remain at temperature 0. The verifier reconstructs the temperature schedule from frozen policy and saved attempts. Each attempt still consumes one explicit proposal slot and at most one model request; there are no hidden retries.
- After full training coverage, six consecutive duplicate responses stop search with `duplicate-stagnation`. Independent final evaluation/review still run. The stop prevents spending the remaining attempt budget on identical instructions; it does not claim improvement or extend any deadline.
- Full validation chooses the best candidate. Ties retain the earliest candidate, including the baseline. Final baseline/selected evaluation and all independent verification still run. Approval requires changed instructions, strict independent validation improvement and no held-out regression.

This permits lateral exploration (同分探索), not a claim that equal scores or text differences establish improvement. Whitespace identity is a duplicate filter, not a semantic novelty metric. Model responses may still be unchanged or invalid. Explicit time, request and metric limits remain hard limits; no retries or automatic continuation are added.

## Defaults and resource counts (預設與工作量)

For the shipped 6/3/3 bank:

| Setting | Exploration default | Maximum |
| --- | ---: | ---: |
| Candidate proposals | 12 | 16 |
| Search evaluations | 87 | 120 |
| Requests per repair task, including summary | 10 | 12 |
| Whole workflow seconds | 7200 | 7200 |

The default search ceiling is three initial validation tasks plus twelve iterations of two parent training tasks, two candidate training tasks and three validation tasks. Twelve final rollouts are separately required. Total capacity is 99 rollouts, 1002 model requests and 297 trusted verifier batches. At sixteen proposals the corresponding search planning figure is 115; increasing the proposal limit alone does not enlarge an already configured metric limit.

For edited banks, the GUI derives defaults from current counts, bounded by 120 search evaluations and sixteen proposals. Submission requires enough proposal slots and metric capacity for a first complete training epoch, conservatively reserving full batches and validation. The GUI shows the same blocker. A bank too large for these bounds requires fewer enabled questions or standard mode; it is not silently truncated.

Each rollout performs immediate verification, evaluator replay and reviewer replay. The GUI exposes the total work before submission. Time capacity does not reserve enough wall-clock time to consume every request slot. Slower models can hit the two-hour cap before all candidates are generated. Historical Runs and uncertain submissions retain their frozen settings. Explicit standard mode and API submissions omitting `searchMode` retain perfect-score skipping. Smoke/Full support explicit exploration without promising full training coverage within their smaller presets.

GUI defaults, including final work and all three verifier passes:

| Profile | Search / proposals | Final rollouts | Total rollout ceiling | Calls/task | Global requests | Verifier batches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke exploration | 10 / 2 | 12 | 22 | 8 | 178 | 66 |
| Full exploration | 26 / 1 | 60 | 86 | 8 | 689 | 258 |
| Shipped bank exploration | 87 / 12 | 12 | 99 | 10 | 1002 | 297 |

Standard Smoke keeps 8/2/1800 seconds. Full keeps 26/1/7200 seconds. Bank standard keeps 10/1/3600 seconds. Switching modes does not mutate an already frozen pending request. The bank still requires capacity for a complete first training epoch before dispatch. Existing datasets, Python policy, model versions, final comparisons and approval gates are unchanged.

## Evidence and inspection (證據與查詢)

The result panel reports training coverage, generation attempts, different new bodies, duplicate bodies and newly validated candidates. These counts derive from saved authoritative rollout/proposal/search artifacts during trusted verification. A duplicate of the baseline counts as a duplicate, not a new instruction.

Every attempt retains its parent, full instruction, diff, strategy, seed, model/settings, actual reflection temperature, training references and budget use. New search results report `skippedDuplicates` and `savedCandidateEvaluations`. History labels first appearances and repeated bodies separately from a change relative to the parent; sixteen changed records can still represent one distinct new body. Diagnostic Skill artifacts also project saved review counts/eligibility without replay, exposing final validation/held-out results while excluding raw model/task content. Search audit separately retains acceptance/rejection and stopping conditions. Read-only history and the diagnostic ZIP accommodate sixteen proposals within their existing aggregate byte ceilings; warnings still identify omitted previews. Archived attempts, accepted search candidates and approved releases remain separate.

Zero-proposal completion is labeled **未產生候選・尚未完成有效比較**. A perfect validation score is no longer described as proof that the entire question bank has no improvement headroom.

## Verification graph and limits (驗證執行圖與限制)

Run exact checks using the pinned environment:

```bash
.venv-nanobot/bin/python scripts/run_test_module.py gepa_exploration_test.py
.venv-nanobot/bin/python scripts/run_test_module.py exploration_workflow_test.py
```

The contract module covers coverage, distinct strategies, failure memory, whitespace duplicate identity, temperature escalation, pre-dispatch limits, HTTP forwarding, neutral acceptance, retained ZIP history and native GEPA controls. An actual-search control produces one new body then six duplicates: only 22 metric evaluations, twelve avoided child evaluations, complete 6/6 training coverage, baseline retained on a tie and an explicit stagnation stop. Native Smoke and Full controls both propose a candidate from perfect training scores.

The exact integration leaf remains `exploration_workflow_test.ExplorationWorkflowTests.test_exploration_perfect_training_duplicate_retention_full_coverage_review_and_approval`. Its graph is test runner → RuntimeService → coordinator → native GEPA worker → fresh nanobot repair processes → evaluator → reviewer → explicit verification → approval verification. Visible-test tools and trusted batches launch `repair_evaluator.py` with their unchanged five-second parent bound.

The frozen integration ceiling is 31 search plus 12 final rollouts, 262 request slots at ten seconds each and three trusted batches per rollout. Startup 120 seconds + requests 2620 + tools/replays 860 + cleanup 30 = 3630 workflow seconds; terminal collection reserves 30 more. Post-completion verification, approval verification, bounded history/export and the ten-second JS consumer remain outside the workflow and within the 7200-second module cap.

Four scripted reflections yield two new bodies and two duplicates. The actual graph is 21 search plus 12 final rollouts, 99 workflow verifier batches, and temperatures 0.7/0.7/0.7/1.0. Both duplicates avoid child evaluation (four rollout savings); every task request stays at temperature zero. The fixture proves independent improvement, approval and tamper rejection using scripted loopback replies, not a real-model evolution gain.

The JS-to-Python SDK case explicitly uses eight search evaluations and six task calls to stay inside its existing frozen fixture budget. The GUI defaults and actual submitted fields are checked separately. The legacy API perfect-seed case still skips proposals and refuses approval. Shared repair completion and historical/export checks remain separate. No broad M7, Windows/GPU or real-model qualification is implied.

## Local validation scope (本地驗證範圍)

The focused Python checks passed 65 cases with zero skips: 11 exploration contracts, 9 archive/export cases, 13 diagnostic cases, 11 bank cases, 8 workload cases, 10 repair completion cases, one complete new exploration SDK workflow, one actual JavaScript/API SDK workflow and one unchanged-standard perfect-seed SDK workflow. The latter two also passed together in a single-host concurrent control. Initial separate tool-launched concurrent jobs observed stale child journal snapshots and were rejected by replay; their original failure evidence is retained. No verification requirement was relaxed, and neither the isolated reruns nor the shared-host concurrent control required runtime source changes. This does not qualify arbitrary parallel deployments or Windows filesystem durability.

All 137 frontend cases passed with zero skips. Ruff, the source credential-pattern scan and whitespace/diff validation passed. Tests use pinned SDKs and scripted loopback replies. Real Ollama/Strata gains, Windows stability, Docker execution and broad M acceptance require their own evidence.
