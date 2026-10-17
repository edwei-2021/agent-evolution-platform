# Versioned Python challenge bank (多難度 Python 題庫)

The GUI includes 12 original repair challenges, a local question editor, and a **多難度題庫** GEPA profile. Finishing an experiment does not imply a new Skill. A perfect seed can leave GEPA with no measurable improvement and zero proposals. More offsets of the same easy program do not establish broader repair capability.

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
6. In **GEPA 技能最佳化**, choose **多難度題庫** and inspect the displayed work ceilings before explicit submission. Initial counts are 6 training, 3 validation and 3 held-out tasks. Presets are 10 search evaluations, 1 proposal, 10 calls per task and 3600 seconds. These are ceilings, not a promise that a particular GPU/model will finish in time.
7. Inspect **實際演化成果**, **依難度與題目面向查看成效**, source-change history and Skill history. No samples means **無題目**, not a perfect score. A releasable new Skill requires a changed body, independent validation improvement and no held-out regression. Approval remains explicit.

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
