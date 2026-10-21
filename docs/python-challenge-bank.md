# Versioned Python challenge bank (多難度 Python 題庫)

The GUI includes 12 original repair challenges, a local question editor, and a **多難度題庫** GEPA profile. Finishing an experiment does not imply a new Skill. A perfect seed can leave GEPA with no measurable improvement and zero proposals. More offsets of the same easy program do not establish broader repair capability.

## Sixty-question V3 catalog (60 題分級題庫)

V3 now supplies **60 tasks: 20 easy, 20 medium and 20 hard**, retaining the twelve V2 IDs and adding 48 original programs. It includes 123 public and 259 retained examples. See [the complete catalog, grading criteria, fixed splits and verification scope](python-challenges-v3-catalog.md).

Choose **均衡批次 1–5** and click **載入 60 題並啟用所選批次**. Each explicit selection enables 6/3/3 tasks, with four questions from every difficulty. Five disjoint batches cover the entire catalog; related groups never change their split between batches. All other stored questions are disabled, not deleted. Existing edits and frozen V1/V2 Runs remain intact. The schema accepts V1, V2 and V3 snapshots. Selected catalog questions with edited split/difficulty/group require restoring those fields or manual enablement, preventing a batch from silently violating its grouping contract.

`POST /api/v1/challenges/presets/repair-v3` accepts only `expectedRevision` and an integer `batch` in 0..4 through the existing localhost/origin/token boundary. First import validates missing questions before an atomic revision update. Later batch switches preserve bodies/references/cases and add no duplicates. The existing 100 stored / 50 enabled-per-run limits and 6/45/7200 exploration defaults remain unchanged. Difficulty filters and total counts include disabled older/custom questions, so the stored total may exceed the catalog's 60.

## Multi-defect V2 update (多缺陷題庫 v2)

The October 19 Strata Run `RUN-bb2efa32-1065-4571-b4fe-e365dfd379cd` generated twelve distinct instructions and completed all 87 search evaluations, but selected baseline index 0. Nine candidates tied at 3/3 search validation, three scored 2/3. The baseline's 3/3 is inferred from the pinned highest-score/earliest-tie selection rule. Search took about 101 minutes; the two-hour deadline stopped the last of twelve independent final tasks, before evaluator replay and reviewer replay. This is evidence for candidate diversity and a saturated small validation split, not a completed improving release.

The new bank exploration default is **6 proposals / 45 search evaluations / 10 calls per task / 7200 seconds**. For 6/3/3 tasks: 45 search + 12 final = 57 rollout slots, 576 request slots and 171 trusted batches across immediate, evaluator and reviewer passes. Historical settings remain frozen. The reduced workload reserves more practical room for final work; the same hard deadline can still expire on a slower model or harder task. No retry, resume, time extension or weaker approval gate was added.

Open **多難度 Python 題庫 → 套用多缺陷題庫 v2** to explicitly install `data/python-challenges-v2.json`. This performs bounded local reference validation, disables old questions and appends/enables twelve new questions. It preserves all existing question text, references and cases, including user edits; the visible editor warns that its unsaved draft will be cleared on success. A second install or ID collision is rejected rather than overwriting edits. Restart alone never installs V2. Existing databases retain V1 and receive only a version-column schema migration; existing frozen V1 datasets remain readable and hash-checked. No model request is made by preset installation.

The new enabled bank is **6 training / 3 validation / 3 held-out** with distinct declared groups:

| Split | New challenge | Principal defects and edge cases |
| --- | --- | --- |
| Train | Quoted field scanner | Escaped quotes, closing state, trailing empty fields |
| Train | Event sessionization | Unsorted input, duplicate timestamps, inclusive gap |
| Train | LRU cache | Get recency, updates, zero capacity |
| Train | Dependency layers | Same-layer unlocking, cycles, duplicate edges |
| Train | Integer expression | Operator precedence, token boundaries, invalid syntax |
| Train | Grid paths | Equal-length shortest paths, blocked endpoints, bounds |
| Validation | Escaped glob matching | Wildcards matching empty text, escaping, whole-text DP |
| Validation | Atomic inventory | Intermediate failure, rollback, absent keys |
| Validation | Temporal load | Simultaneous events, strict thresholds, earliest peak |
| Held-out | Tree path encoding | Iterative traversal order, escaping, duplicate keys |
| Held-out | Resizable buffer | Shrinking keeps newest, zero capacity, nonrestoration |
| Held-out | Bounded change | Stock limits, combination counts, unreachable targets |

These are original tasks with interacting defects and explicitly specified edge behavior, not renamed V1 templates. Expected outputs are authored independently of the reference implementations; both visible and retained cases are checked. Every erroneous start must fail at least one retained case as well as the existing faulty-start check. Reference code stays outside frozen model fixtures; validation and held-out trajectories never enter reflection. Declared group uniqueness does not prove absence of every semantic overlap.

V2 uses the existing `python-challenge-v1` syntax/evaluator policy without adding Python privileges. Difficulty labels are estimates (six medium and six hard tasks), **not target-model calibration**. Run the smaller experiment with the same provider/model/settings and examine baseline validation, retained performance, call caps and source rejections. If baseline again reaches 3/3, do not claim a useful success-rate gradient or repeatedly tune against these held-out cases; create another version with fresh independent cases. Instruction length or more candidates alone is not improvement.

`POST /api/v1/challenges/presets/repair-v2` accepts only `expectedRevision` and uses the existing localhost/origin/token boundary. Twelve serial validation subprocesses each retain a five-second parent bound (60 seconds total); the GUI reserves a 90-second HTTP wait without extending any workflow. Revision is checked before validation and again under the write lock. Duplicate install, stale revision, invalid fields or failed validation cannot partially update the bank. Catalog GETs, navigation and rendering remain read-only.

The focused execution graph is test runner → RuntimeService → coordinator → pinned GEPA worker → fresh nanobot task processes and `repair_evaluator.py` tool/batch subprocesses → independent final tasks → evaluator replay → reviewer replay → explicit approval verification. The new exact V2 integration has a 22-rollout/133-request ceiling, ten-second requests, at most 24 five-second visible-test tools per task and three five-second trusted batches per task. Startup 120 + requests 1330 + tools/replays 2970 + cleanup 30 = **4450 workflow seconds**; terminal collection adds 30, approval replay reserves 110, and the ten-second JS consumer plus preset validation fit the existing 7200-second module cap. The scripted fixture actually uses three tools/one public-test invocation per repaired task; exact counts are asserted. The oracle/HTTP migration module separately bounds each validation subprocess and uses a 70-second local HTTP wait.

Local verification passes 40 distinct Python cases with zero skips: six V2 oracle/migration/API cases, one V2 SDK workflow, eleven V1 bank cases, one V1 SDK workflow, one exploration SDK workflow, twelve exploration contracts and eight workload/manifest cases. All 139 frontend cases pass, as do Ruff, source credential-pattern and whitespace checks. An initial retained-case assertion exposed that the dependency-layer baseline still passed its original five retained cases; a chain ordered by prerequisites now specifically detects same-layer unlocking. The final oracle and V2 SDK checks pass with that added case. The published V2 pack has 27 visible and 62 retained examples; prior failed test evidence remains in local reports.

Read-only source hashes are frozen before actual SDK checks. V1 workflow and V2 workflow cases run sequentially; each has its own frozen dataset. Copied isolated-evaluator checks cover all V2 reference cases without site packages. Frontend checks exercise the actual install button and POST, pending-request preservation, new default payload, version acceptance and dynamic counts. Scripted loopback improvement qualifies implementation behavior only; no Windows/GPU, Docker execution, full M acceptance or real-model gain is claimed.

## Research and scope (研究依據與範圍)

- [EvalPlus, Liu et al.](https://arxiv.org/abs/2305.01210): insufficient tests can miss incorrect programs. Each challenge includes public and retained edge cases, a checked reference and a genuinely defective starting program.
- [BigCodeBench, Zhuo et al.](https://arxiv.org/abs/2406.15877): diverse operations and complex requirements reveal capabilities beyond a short formula. This bank covers text, collections, state, parsing, ordering and search, without BigCodeBench's external-library workload.
- [GEPA, Agrawal et al.](https://arxiv.org/abs/2507.19457): reflection uses execution feedback to evolve instructions. This integration retains training-only reflection, validation selection and independent final evaluation.

These are **original adaptations of evaluation principles**, not downloaded benchmark questions, official difficulty ratings or reported benchmark scores. No benchmark code or question text was copied. Difficulty labels are author estimates; calibrate them using the same saved model and budgets. A stronger model may solve every question, and a weaker model may fail every question. Neither extreme supplies good evidence for useful prompt evolution.

## Shipped questions (內建題目)

| ID | Difficulty | Aspect and defect | Default split |
| --- | --- | --- | --- |
| CH-normalize-whitespace | Easy / 初階 | Text; repeated and Unicode whitespace | Train |
| CH-stable-deduplication | Easy / 初階 | Collections; order lost while removing duplicates | Train |
| CH-frequency-table | Medium / 中階 | Hashing; repeated values overwritten | Train |
| CH-chunk-sequence | Medium / 中階 | Partitioning; dropped tail and invalid size | Train |
| CH-binary-search-first | Hard / 進階 | Search; first duplicate and absent values | Train |
| CH-merge-intervals | Hard / 進階 | Intervals; touching, nested and reversed bounds | Train |
| CH-balanced-brackets | Medium / 中階 | Stack; bracket order and nesting | Validation |
| CH-median | Medium / 中階 | Statistics; sorting, even length and empty input | Validation |
| CH-signed-decimal | Hard / 進階 | Parsing; strict decimal grammar and invalid forms | Validation |
| CH-run-length-encode | Easy / 初階 | Encoding; adjacent runs versus global counts | Held-out |
| CH-prefix-balances | Medium / 中階 | Accumulation; initial state and successive balances | Held-out |
| CH-stable-record-sort | Hard / 進階 | Ordering; multiple keys and stable ties | Held-out |

`data/python-challenges-v1.json` is inserted only when the local database has no bank record. Restarting does not restore deletions or overwrite edits. Existing Smoke and Full datasets remain separate.

## Operate the GUI (實際操作)

1. Stop the GUI, update the checkout, then run `bash scripts/start-gui.sh`. Existing optional `~/strata-wsl.env` initialization remains available.
2. Open **多難度 Python 題庫**. Select a question to edit, choose **新增題目**, or use **刪除** and its confirmation. The list supports difficulty filtering and enabling/disabling questions.
3. Supply a title, difficulty, aspect, related-question group, split, requirement, erroneous starting program, reference, public tests and retained tests. References and cases are visible to the local operator. Reference code is excluded from frozen GEPA fixtures and model prompts; retained tests are unavailable to repair tools.
4. Choose **驗證並儲存題目**. The reference must pass every case and the start must fail at least one. Invalid JSON and evaluation errors preserve the draft. Saving calls no model.
5. In **框架整合**, select and save Ollama or Strata. Set maximum output tokens to **1024** initially for the bank; values below 512 are rejected before cold SDK discovery. This recommendation does not automatically increase saved limits. A short output cap can truncate a valid repair.
6. Click **準備題庫演化** on the bank or single-repair page. This selects **多難度題庫** in GEPA and shows its revision/counts without calling the model. Inspect settings and work ceilings, then explicitly click **開始題庫演化** to submit. Initial counts are 6 training, 3 validation and 3 held-out tasks. The GUI now defaults to [multi-candidate exploration](gepa-exploration.md): 45 search evaluations, 6 proposal slots, 10 calls per task and 7200 seconds for this bank. The standard mode retains 10/1/3600. These are ceilings, not a promise that a particular GPU/model will finish in time.
7. Inspect **實際演化成果**, **依難度與題目面向查看成效**, the per-question attempt table, frozen-bank coverage, source-change history and Skill history. No samples means **無題目**, not a perfect score. A releasable new Skill requires a changed body, independent validation improvement and no held-out regression. Approval remains explicit.

Use train cases with meaningful feedback and attainable successes. Keep related programs in the same group and split. The group check catches declared overlap, not semantic duplicates; authors must identify related templates. Do not rewrite held-out cases after every candidate's mistakes and claim an unchanged benchmark. Edits create a new revision; cross-revision scores are not a controlled comparison.

## Task contract and limits (題目格式與限制)

The opt-in `python-challenge-v1` policy accepts exactly `solve(data)` with bounded JSON input/output. Each task explicitly overrides the generic legacy Skill's `clamp` example. Legacy integer-function policy remains separate.

Supported syntax includes loops, branches, indexing/slicing, lists, dictionaries, sets and allowlisted pure builtins/data methods. Imports, files, network, shell, classes, recursion, comprehensions, decorators, indirect calls and private attributes are unavailable. Expected exceptions support only `ValueError`, with or without constructor arguments; no chaining. `scripts/challenge_policy.py` contains the exact allowlist.

Both public (`visible`) and retained (`hidden`) arrays require 2–20 cases each:

```json
[
  {"input": {"items": [1, 2, 3], "size": 2}, "expected": [[1, 2], [3]]},
  {"input": {"items": [1], "size": 0}, "raises": "ValueError"}
]
```

Numbers must be finite and bounded. Numeric results use relative and absolute tolerance `1e-9`; booleans are distinct from numbers. Input preservation uses exact values and types. Every case resets the namespace and deep-copies input. Unsupported return values cannot impersonate expected exceptions.

Limits: 8 KB source, 1000 AST nodes, 64 KB/question, 100 stored questions and 50 enabled/run. Each experiment split needs at least two tasks; training allows 30, validation/held-out 20 each, and validation plus held-out at most 30. This preserves existing total-call bounds. CRUD and GETs do not import SDKs or dispatch models. Explicit saves validate references/starts in existing evaluator subprocesses with 2 CPU seconds, 256 MiB address space and 5-second parent bounds. This native policy is not an operating-system sandbox for arbitrary Python.

Mutations use localhost/origin and token checks plus expected revision. Stale editors/submissions fail instead of overwriting newer data. Every run freezes enabled questions, splits, version, revision and hash, excluding reference source. Later edits/deletions do not alter current/historical experiments. Read-only history accommodates the larger configuration while retaining its 8 MiB aggregate read bound.

## Verification and maintenance (驗證與維護)

Focused checks cover all 12 reference oracles and faulty starts, unsafe/neighboring syntax, non-JSON outputs, exact input preservation, bounded reference failure, persisted CRUD, revision conflicts, origin/token gates, frozen isolation and history. Frontend tests exercise actual app forms, draft preservation, deletion, submission payloads and work counts.

An exact integration uses **real pinned nanobot and GEPA SDK processes with scripted loopback model replies**. It covers proposals, repair, immediate/evaluator/reviewer verification, final comparisons, difficulty/aspect totals, JavaScript result validation, editing the live bank during a run, approval and tamper rejection. This proves implementation behavior, not Strata/Ollama improvement. Its ceiling is 22 rollouts, 133 requests and 66 verifier batches; 4450 workflow seconds derive from serial bounded model calls, visible tools, all three verification passes and cleanup. Legacy perfect-seed/no-release and hidden-regression paths are checked separately.

The copied evaluator includes `challenge_policy.py` and its source hash. Its isolated staged entrypoint is tested without site packages. Docker users need a newly built immutable image for this policy. These checks do not claim running Docker validation, broad M7 acceptance, browser visual qualification or Windows/GPU evolution results.

Common maintenance failures to prevent:

- Do not equate completion, a changed prompt or proposal count with improvement. Show trusted scores and distinguish approval/activation.
- Audit write mediation, independent evaluation, reviewer replay, child configuration and copied payload before enabling new task syntax.
- Check both correct references and genuine faulty starts; retained edge cases must cover the specified behavior.
- Keep catalog edits immutable per run, related groups within one split, and reference code outside model fixtures/reflection.
- Audit read bounds when frozen datasets grow; omit retained cases from read-only change projections.
- Freeze hashed runtime source before integration checks. Editing it during a running case intentionally triggers provenance rejection; finish the exact affected checks without concurrent source edits.
- Count final rollouts and all three verification passes. Preserve submitted deadlines and original failures; duration estimates are not guarantees.

Possible next extensions include repeated-run difficulty calibration, more independently reviewed edge cases and a separately designed multi-file/library sandbox. They are not implied by these pure-function tasks.

New GEPA experiments produce a [paired final-task comparison](gepa-paired-comparison.md). A net score gain cannot hide a lost baseline success: validation and held-out must both have zero per-task regressions before release. Older saved aggregate verdicts remain historical evidence; viewing the report adds no model calls.

## Execution identity follow-up (執行對象辨識)

A completed single-repair record is evidence for `nanobot-repair` and its fixed clamp fixture; it does not establish a bank GEPA experiment. When diagnosing an apparently instant completion, correlate the current startup session, HTTP submission route, workflow task, model-call metadata and frozen profile. A bank GET, successful save, navigation or historical completed result is not a submitted experiment. Retained logs can prove observations within their covered interval, not actions outside it.

The bank entrypoint now explicitly prepares the bank profile. It performs only a local status read and changes the next-run settings. It does not POST a workflow or silently change model output limits. An unresolved prior GEPA request prevents preparation from relabeling a frozen pending submission. Single-repair controls name the fixed task, and the GEPA page separates next-run bank settings from the identity of existing results. Exact app-handler tests cover preparation from both pages, the low-token disabled state and the final explicit POST with `profile=bank` and the current `bankRevision`.

Bank-specific blockers now appear immediately beside Start, before historical results. The notice displays the actual saved output cap, the 512 minimum and 1024 recommendation, with a direct **框架整合** settings button. Unready-bank errors link to the question editor. Full retains its existing cap policy. Tests cover the Full/bank difference at 256, the 511/512 boundary, escaped bank errors, and the real settings form save followed by an explicit bank submission. An input draft alone does not change the saved cap. Rendering and navigation never increase limits or dispatch a model.

New bank experiments also freeze a narrowly verified per-task call-cap failure policy: an exhausted task remains failed and scores zero while later tasks proceed. Native completion is still required for successful repair; network, evaluator, deadline and integrity failures still stop the workflow. Results list exhausted tasks explicitly. Exact allowlists now appear in the task contract and source-rejection feedback. See [task-cap evidence, journal ownership and regression proof](gepa-task-failure-followup.md).
