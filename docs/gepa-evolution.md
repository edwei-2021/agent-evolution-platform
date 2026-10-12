# GEPA Skill Evolution (技能最佳化)

Release **v0.7.0** implements an actual **GEPA 0.1.4** adapter over the existing **nanobot-ai 0.3.5** runner. GEPA selects and mutates one text component, `skill_body`; each evaluation executes a fresh nanobot Worker and independently measures a bounded Python repair task. Skill name/description, saved model, temperature, tools, dataset version and workflow remain frozen. This is separate from the earlier custom LLM reflection engine.

## Upgrade and run (更新與執行)

Stop the local GUI with Ctrl+C, then run in the WSL checkout:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-nanobot.sh
bash scripts/start-gui.sh
```

Refresh the browser with Ctrl+Shift+R and open `http://localhost:8765/#gepa`. Confirm nanobot and GEPA are available. Save the model in Integrations and explicitly preload it before starting. Begin with **Smoke** to check the complete search/evaluation/review path. Model requests use the saved output-token limit; leave enough room for complete tool-call JSON and Skill-body proposals. Startup and package inspection send no model requests.

The installer adds GEPA to the separate `.venv-nanobot` environment; the stdlib GUI environment remains separate. Processing, temp files and tokenizer/pip caches remain under the project. Existing provider settings, rule versions and LLM prompt versions remain intact. The private hosted Site contains the frontend; Python execution requires the local WSL API.

## Grouped synthetic dataset (依群組分割的合成資料)

`gepa_dataset.py` defines `bounded-python-families-v1`. Full has five offset variants for each operation family; Smoke uses one variant per family. Each family belongs to exactly one split, so offset variants never cross splits.

| Split | Families | Smoke | Full | Use |
| --- | --- | ---: | ---: | --- |
| Training | clamp, absolute-offset, minimum, maximum | 4 | 20 | Reflective feedback and minibatch acceptance |
| Validation | sign, positive-sum | 2 | 10 | GEPA candidate selection; fresh post-search evaluation |
| Final | clipped-sum, span, distance, threshold | 4 | 20 | Post-selection baseline/selected comparison only |

Each task repairs `clamp(value, lower, upper)` according to its own explicit contract, with a deliberately incorrect initial `return value`. Three visible cases are available through `run_tests`; three additional cases are evaluated only after candidate source freezes. Task success requires all six cases to pass. This dataset is handwritten/generated synthetic fixture coverage (合成測試涵蓋範圍), not an external coding benchmark. Families share primitive Python operators; disjoint group assignment does not imply statistical independence or prove performance on real repositories.

## Actual optimizer contract (實際最佳化契約)

The version-pinned integration calls `gepa.optimize` with a custom adapter, explicit training/validation lists, Pareto selection, fixed random seed 0, serial evaluation, no merges and no evaluation cache. The adapter implements:

- `evaluate`: fresh workspace/session and actual SDK calls for every task; score is trusted full-task success, never an agent's text assertion.
- `make_reflective_dataset`: only training task/source/tool/test trajectories, with actionable failures.
- `propose_new_texts`: one bounded no-tool model request through the same saved provider. Require exactly `{"skill_body": "..."}`; freeze name/description and bound the body to 8 KB.

GEPA's own search and acceptance logic decides which proposals enter the candidate pool and selects the highest validation score. Reviewer replay checks the stored pool's full validation evidence, selected index, proposal/model correspondence and SDK metric count. Reflection receives no validation/final trajectories. The search adapter rejects final task IDs. Selection is persisted before the final evaluator starts; final results never feed another proposal.

GEPA 0.1.4 can catch a proposal exception internally. The adapter additionally latches such failures and stops before another proposal or final evaluation. Malformed proposal JSON, provider failures, incomplete SDK turns and accounting failures terminate the experiment. They do not trigger an automatic model retry or release an unverified candidate.

## Budgets and progress (預算與進度)

| Limit | Smoke default | Full default | Enforcement |
| --- | ---: | ---: | --- |
| Search task evaluations | 8 | 80 | Adapter preflight and GEPA stopper |
| Proposal requests | 2 | 4 | Adapter and stopper |
| SDK calls per task | 6 | 6 | Runner and SDK iteration limit |
| Global model calls | 122 | 844 | Includes search, proposals and independent final work |
| Whole-run time | 1,800 s | 1,800 s | Supervisor and runner deadline |
| Per-call time | 120 s | 120 s | Saved provider cap, bounded transport and supervisor |

GEPA checks stop conditions between iterations. Before an iteration starts, reserve its parent/child minibatches plus full validation; the adapter also refuses any batch that would exceed the hard metric cap. Therefore unused budget is normal. Perfect training minibatches may skip reflection, and proposal limits may end search early.

Independent final work reserves **two executions per validation/final task**, one for the frozen baseline and one for the selected Skill. The global call cap is `(metricBudget + 2 * (validationCount + finalCount)) * taskCallBudget + proposalBudget`. Each request pins the output-token ceiling; `maxOutputTokens` records the worst-case output allowance. Ollama provides no monetary billing metric here; the application makes no dollar-cost claim. Model timing and reported usage remain in raw completion/SDK evidence.

The GUI shows role stages, completed/sent model calls, stream chunks/characters, per-call deadline, search evaluations, completed rollouts, proposals and current task. Paused/stale polling is explicit. Cancellation terminates the actual process group and releases the shared provider/workflow slot. Model warmup and other model experiments share exclusion with GEPA. Approval replays evidence without model requests and may take longer for Full; the client allows a bounded two-minute approval wait.

## Evidence and versions (證據與版本)

Run artifacts under `.local/runs/RUN-.../` include:

- `gepa-config.json`: baseline version, model/revisions, SDK versions, limits and code/dataset hashes.
- `gepa-rollouts.json`, `gepa-calls.json`, `gepa-proposals.json`: actual task, global request and reflective feedback accounting.
- `gepa-search.json`, `gepa-selection.json`, `gepa-selection.md`: optimizer result, pre-final frozen selection and exported Skill.
- `rollouts/R.../repair-*`: fresh source, tools, requests/SSE, SDK stop/usage and recomputed test evidence for each task.
- `reflections/P.../repair-calls.json`: the single no-tool proposal request and response.
- `gepa-evaluation.json`, `review.json`: independently recomputed final results and evidence hash.

The module Log page includes GEPA events and nanobot tool/model records correlated with the parent Run ID. Root artifacts are exposed through the existing read-only artifact API; detailed nested rollout files remain available in WSL. The GUI escapes model/Skill text and exports the selected `SKILL.md` without applying solution patches to Git.

Approval requires a completed verified run, a changed Skill, strictly higher **fresh validation task success**, no lower **final task success**, unchanged active baseline and current Skill revision. Approval replays all child/test/proposal evidence and creates an immutable `GSV-...` version. Explicit activation/rollback changes only future GEPA experiments. Rule and LLM versions, the fixed Python repair page and repository code are separate. No automatic activation occurs.

Repeated final-set checks across experiments can guide a human indirectly; treat this fixture as development feedback and reserve a new external test set before making a model-quality claim.

## Scope and next milestone (範圍與下一階段)

The accepted AST is the existing small pure-function subset, evaluated with an isolated interpreter and resource limits. It is not an OS sandbox for arbitrary Python. Only read/write solution and fixed visible tests are granted; shell/network/spawn/MCP tools are never registered. No user Windows/GPU diagnostics are added.

Next: add user-authored grouped tasks and richer trace inspection against this measured contract; arbitrary multi-file repository execution requires a separate container/security design. Authenticated remote workers and external-agent Skill publication remain later work.

Primary API references: [GEPA v0.1.4](https://github.com/gepa-ai/gepa/releases/tag/v0.1.4), [pinned adapter protocol](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/core/adapter.py), [pinned optimize API](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/api.py).
