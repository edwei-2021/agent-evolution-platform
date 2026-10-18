# Multi-candidate GEPA exploration (多候選探索)

The challenge-bank GUI now defaults to exploration. The former standard configuration could consume three validation tasks and two perfect training tasks, skip reflection, then stop because the remaining five metric slots could not reserve a seven-evaluation iteration. Retention alone did not fix that search limitation.

## Search behavior (搜尋行為)

Exploration uses the pinned GEPA 0.1.4 optimizer and the same nanobot 0.3.5 repair runner. It changes candidate search, while preserving the binary trusted task score and independent release gates.

- A queue samples every training task before beginning a new shuffled epoch. A short final batch is allowed. A server-generated seed is frozen per Run and retained for replay; it does not change model temperature or weights.
- Perfect training batches may propose instructions. Sixteen explicit, general repair strategies rotate across attempts: contract, boundaries, permitted syntax, invariants, minimal repair, budgeting, input preservation, recovery, generalization, control flow, test interpretation, concise workflow, representation, stable order, multistep repair and synthesis.
- Reflection receives the parent, actual training trajectories and up to three preceding candidate instructions. No validation or held-out trajectories enter reflection. The existing system prompt still prohibits solution code and task-specific answers.
- A distinct candidate whose training score equals its parent's score may proceed to full search validation. A training regression is rejected. A body already in GEPA's validated population is rejected as a duplicate; the original generated attempt remains archived.
- Full validation chooses the best candidate. Ties retain the earliest candidate, including the baseline. Final baseline/selected evaluation and all independent verification still run. Approval requires changed instructions, strict independent validation improvement and no held-out regression.

This permits lateral exploration (同分探索), not a claim that equal scores establish improvement. Model responses may still be unchanged or invalid. Explicit time, request and metric limits remain hard limits; no retries or automatic continuation are added.

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

Each rollout performs immediate verification, evaluator replay and reviewer replay. The GUI exposes the total work before submission. Time capacity does not reserve enough wall-clock time to consume every request slot. Slower models can hit the two-hour cap before all candidates are generated. Historical Runs and uncertain submissions retain their frozen settings. Smoke/Full and API submissions omitting `searchMode` retain standard behavior.

## Evidence and inspection (證據與查詢)

The result panel reports training coverage, generation attempts, different new bodies, duplicate bodies and newly validated candidates. These counts derive from saved authoritative rollout/proposal/search artifacts during trusted verification. A duplicate of the baseline counts as a duplicate, not a new instruction.

Every attempt retains its parent, full instruction, diff, strategy, seed, model/settings, training references and budget use. Search audit separately retains acceptance/rejection and stopping conditions. Read-only history and the diagnostic ZIP accommodate sixteen proposals within their existing aggregate byte ceilings; warnings still identify omitted previews. Archived attempts, accepted search candidates and approved releases remain separate.

Zero-proposal completion is labeled **未產生候選・尚未完成有效比較**. A perfect validation score is no longer described as proof that the entire question bank has no improvement headroom.

## Verification graph and limits (驗證執行圖與限制)

Run exact checks using the pinned environment:

```bash
.venv-nanobot/bin/python scripts/run_test_module.py gepa_exploration_test.py
.venv-nanobot/bin/python scripts/run_test_module.py exploration_workflow_test.py
```

The first module has seven cases. Its native GEPA control uses an in-memory evaluator and creates twelve distinct candidates from perfect training scores: 87 metric calls, all six training IDs covered, thirteen fully validated instruction bodies including the baseline, and baseline retained on a tie. Other cases test short batches, distinct seeds, pre-dispatch coverage gates, the actual HTTP route, duplicate/regression acceptance and sixteen-record diagnostic ZIP retention.

The exact integration leaf is `exploration_workflow_test.ExplorationWorkflowTests.test_exploration_perfect_training_duplicate_retention_full_coverage_review_and_approval`. Its execution graph is test runner → RuntimeService → coordinator → native GEPA worker → fresh nanobot repair processes → evaluator → reviewer → explicit verification → approval verification. Each repair's visible-test tool and trusted verifier launch `repair_evaluator.py` under its existing five-second parent bound.

Its frozen ceiling is 24 search plus 12 final rollouts, 219 model-request slots at ten seconds each, one visible-test subprocess per scripted repair, and three trusted batches per rollout. Startup 120 seconds + requests 2190 + tools/replays 720 + cleanup allowance 30 = 3060 workflow seconds. Terminal collection allows 30 additional seconds. Two post-completion verification passes, bounded history/export reads and a ten-second JavaScript consumer are outside that workflow; the case remains within the release supervisor's 7200-second module bound. The actual graph is 21 search plus 12 final rollouts and 99 workflow verifier batches. Every generation receives perfect training feedback; three proposals yield two distinct validated bodies and one retained duplicate. Coverage, release approval, ZIP export, actual JavaScript validation/rendering and tamper rejection are asserted.

The legacy bank integration remains a separate module with its existing 4450-second bound, avoiding a combined parent that cuts off the new case. The standard perfect-seed case remains separately selected under `gepa_validation_budget.py`; it still skips proposals and blocks approval. No broad phase-M, Windows/GPU or real-model improvement claim follows from these scripted loopback checks.

Focused local validation passed 57 frontend cases and 49 Python/API/SDK cases: seven exploration contracts, eight archive cases, twelve saved-history cases, eleven bank cases, eight workload/manifest cases and the three exact SDK workflows described above. Ruff, the source credential-pattern scan and diff checks passed. The workload test's stale twelve-case GEPA manifest assertion was corrected to the thirteen cases already present before this change; production supervision was not widened. The eighteen-entry source-history consumer (baseline + sixteen proposals + selection/pending) is checked using the actual Python projection and JavaScript validator.
