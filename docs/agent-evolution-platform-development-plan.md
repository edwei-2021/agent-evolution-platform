# Agent Evolution Platform — Revised Development Plan
## 1. Revision and Execution Baseline
- Plan revision: 2.0; assessment date: 2026-10-12 (Asia/Taipei).
- Product name: Agent Evolution Platform (代理人演化平台).
- Current repository: `edwei-2021/nanobot-gepa-mvp`.
- Target repository name: `edwei-2021/agent-evolution-platform`; the rename is a repository administration operation, separate from this documentation commit.
- Reviewed implementation baseline: v0.7.1, commit `19f6a4fa3a3b4da400e59b4c692d56b68711f29f`.
- This revision supersedes the uploaded six-phase development specification as the execution roadmap. Historical guides remain valid for their version-specific features.
- Evidence basis: repository README, GEPA guide, accelerated delivery plan, GEPA evidence verifier, and baseline commit metadata. Existing test reports are historical evidence; no new runtime regression or Windows/GPU test was performed for this planning revision.
- GitHub currently reports the repository as public. This plan does not change visibility. The hosted GUI has a separate private access policy.
- Status labels: **Implemented** means bounded functionality exists in the reviewed baseline; **Partial** means useful components exist but the new phase gate is unmet; **Planned** means no completed implementation is established. None of these labels certifies production readiness.

## 2. Objective and Scope
Build a self-hosted platform with two isolated evolution loops:
1. GEPA evolves one named Skill body under a fixed workflow.
2. OpenEvolve later evolves a declarative workflow under a fixed approved Skill set.

Share one control API, runtime-neutral adapter contract, independent evaluator, durable evidence model, GUI and release service. Release a compatible bundle of Skill set, workflow, runtime/model/tool policy, evaluator/dataset version and memory snapshot. Activate for new runs and roll back without modifying historical evidence.

Selected first MVP: nanobot + GEPA, one agent, `python-fix-and-verify`, one fixed task workflow. Retain current rule and LLM reflection experiments as explicitly labeled legacy/development tools. OpenClaw follows the trusted MVP; Hermes/Herdr and NanoClaw follow capability verification.

## 3. Completed Work — Preserve and Reuse (已完成成果)
| Capability | Status and current boundary | Evidence/reference |
| --- | --- | --- |
| Windows Ollama configuration | Implemented: persisted model/endpoint/timeouts, gateway discovery and proxy bypass; no automatic connection diagnostics | README; docs/ollama-wsl.md |
| Model preload | Implemented: explicit asynchronous warmup, cancellation and load timing; successful warmup does not guarantee continued residency | docs/module-logs.md |
| Observable inference | Implemented: streaming model responses, sent/completed counts, elapsed time, absolute deadlines and cancellation | docs/verification/llm-progress-validation.md |
| Module and step logs | Implemented: bounded SQLite journal, filtering/export, correlated spans and durations; retention can remove history | docs/accelerated-plan.md |
| Local role supervision | Implemented: actual processes, PID/status/logs and backend run history | README |
| Rule and LLM Skill experiments | Implemented: separate measured rule search and custom model reflection, evidence checks and local version rollback | docs/skill-evolution.md; docs/llm-skill-evolution.md |
| nanobot repair runner | Implemented: nanobot-ai 0.3.5, fresh workspace/session, three controlled tools, diff and independently recomputed tests | docs/nanobot-repair.md |
| GEPA Skill-body search | Implemented: GEPA 0.1.4, frozen configuration, actual nanobot task evaluations, bounded proposals and search | docs/gepa-evolution.md; scripts/gepa_engine.py |
| Grouped synthetic dataset | Implemented: Full 20/10/20, Smoke 4/2/4, family-based split; narrow pure-function coverage | docs/gepa-evolution.md |
| Local candidate versions | Implemented: evidence replay, human approval, explicit activation and rollback; distinct stores for rule/LLM/GEPA | docs/gepa-evolution.md |
| Faster trusted evaluation | Implemented: bounded batches with fresh namespaces; reported local evaluator speedup is not model/inference speedup | docs/accelerated-plan.md |
| Staged checks | Implemented: quick/model/release profiles; release requires installed pinned SDKs | scripts/check_steps.py; docs/accelerated-plan.md |

Historical v0.7.1 commit reports 207 distinct checks. This revision does not re-certify that report or claim new model-quality results.

### Current limitations
- Frontend: buildless native JavaScript; backend: local Python service. React/TypeScript and FastAPI are target migrations.
- The hosted Site serves static GUI assets; real Python/Ollama execution requires the local WSL API. A private Site login does not authenticate or secure that API.
- The constrained AST evaluator is not an OS sandbox for arbitrary Python.
- Existing local version activation is not a signed, complete, cross-runtime release manifest.
- Current GEPA eligibility compares aggregate pass counts; equal totals can conceal individual regressions.
- Current task families are synthetic and share primitives. Family separation does not establish broad coding generalization.
- Current debug retention and best-effort spans do not provide an append-only authoritative evidence ledger.
- Browser-local role configuration does not change the fixed backend workflow.

## 4. Revised Phase Map
Keep the original six phases as target capability groups. Insert mandatory **Intermediate Phase M — Compatibility and Trust Hardening (相容性與可信度補強)** before expanding the existing MVP.

| Original phase | Current status | Revised execution |
| --- | --- | --- |
| P1 Foundation/contracts | Partial | Reuse installers/logging; complete M1/M2/M7 |
| P2 Control plane/evidence | Partial | Reuse API/supervisor/GUI; complete M2/M3/M7 |
| P3 nanobot/trusted evaluator | Partial | Reuse SDK/tools/fixtures; complete M4/M5 |
| P4 GEPA/controlled release | Partial | Reuse real optimizer; complete M5/M6, then P4 closure |
| P5 Workflow evolution | Planned | Begin after trustworthy P4 closure |
| P6 Multi-runtime operations | Planned | Add OpenClaw first, then remaining adapters |

No implementation phase is declared complete solely because a version exists. Record gate evidence against exact source, dependency and dataset hashes.

## 5. Intermediate Phase M — Required Missing Work (中間階段：待補做項目)
Deliver small compatible releases. Keep existing settings, saved versions, runs, explicit warmup, progress/log views and cancellation usable throughout.

| Step | Required implementation | Machine-executed gate | Failure code |
| --- | --- | --- | --- |
| M1 Baseline and compatibility | Inventory APIs/stores; freeze baseline hashes; backup/restore guide; migration fixture and original-feature regression matrix | Pinned quick/model/release checks and restore test produce artifacts; no skipped SDK test accepted as pass | DBG-M-001 |
| M2 Canonical contracts | Pydantic models and generated TypeScript for Task, Run, Evaluation, Candidate, Experiment, Release, Event, StepCheck; wrap existing runners | Mock and nanobot contract suite covers success, failed execution, timeout, cancellation, malformed output; requested/loaded Skill hashes match | DBG-M-002 |
| M3 Durable lifecycle | SQLite migrations, authoritative event ledger, idempotency keys, worker leases, restart reconciliation, persist-before-deliver SSE replay | Duplicate submission creates one logical job; crash/restart recovers or marks interrupted; reconnect has no missing logical events; duplicate delivery deduplicates by sequence | DBG-M-003 |
| M4 Evaluator isolation | Container runner, read-only protected evaluator mount, separate candidate workspace, network/tool/resource policy, immutable test image, diff/cleanup | Known-good/bad fixtures yield expected verdicts; malicious fixture cannot access protected paths; resource failure and cleanup failure quarantine the run | DBG-M-004 |
| M5 Dataset and comparison | Task import/linter, immutable 20/10/20 manifest, family/fixture hash checks, feedback sanitizer, repetitions, per-task regressions and uncertainty report | Reject leakage, mutated snapshots and unsafe feedback; one lost baseline success blocks release under zero-regression policy | DBG-M-005 |
| M6 Release and checkpoint | Content-addressed assets, restartable experiment checkpoint, separate budgets, complete manifest, approval identity, atomic activation/rollback | Resume reuses completed work without duplicate committed results; unauthorized activation fails; in-flight runs retain snapshots; rollback restores whole bundle | DBG-M-006 |
| M7 Reproducible operations | FastAPI compatibility facade, uv lockfile, Compose profiles, health checks, CI, correlation/redaction, support bundle and retention separation | Fresh bootstrap/check succeeds; DB migrations round-trip on fixtures; correlation reaches API/worker/evidence; secret scan and protected evidence retention pass | DBG-M-007 |

### M dependency order and increments
- Increment M-A: M1 + M2 + M7 minimum bootstrap/API/CI portion.
- Increment M-B: M3 + M4; depends on M-A.
- Increment M-C: M5 + M6 + remaining M7; depends on M-B.
- Repository naming and this plan revision do not certify any M gate.
- Each increment migrates existing data with a tested backup and rollback path. Historical bounded runs retain their original capability labels; missing fields are not fabricated.

### M exit criteria
One operator can run a fixed nanobot baseline and bounded GEPA experiment through the existing GUI with canonical persisted evidence, isolated tests, safe feedback, restart handling, per-task regression gates and a complete rollbackable release. Failed authoritative persistence blocks advancement. Best-effort debug logging remains supplementary.

## 6. Practical Architecture and Migration Policy
| Layer | Initial hardened local stack | Later expansion trigger |
| --- | --- | --- |
| GUI | Existing JavaScript with compatible API; incrementally migrate to React/TypeScript | Contract stable and feature migration has browser regression evidence |
| API/contracts | FastAPI + Pydantic facade around current services | Remove old handlers after compatibility migration |
| Evidence DB | SQLite + explicit migrations, transactions and immutable logical records | PostgreSQL for concurrent operators/workers or remote service |
| Artifacts | Local content-addressed store with verified hashes | S3-compatible storage for shared workers and retention |
| Worker dispatch | Durable local queue and leases | Redis + Celery/Dramatiq when distributed queue is required |
| Evaluator | Docker/Compose worker/evaluator isolation | Stronger sandbox or remote execution after threat/capability review |
| Observability | Correlated persisted events + existing module/step logs | OpenTelemetry integration after authoritative event model |
| Environment | Python 3.11+, uv, pinned nanobot/GEPA; current supported Node for legacy GUI | Target frontend uses Node 20+ subject to chosen package support |

Do not require a simultaneous React/PostgreSQL/Redis/S3 rewrite. Keep bounded pure-function mode available while container mode is added. Docker availability, mount behavior and resource controls must be verified on the user's WSL deployment before claiming local sandbox readiness.

## 7. Canonical Execution, Evaluation and Evidence Rules
### Execution contract
`run(task, release_snapshot, environment_snapshot) -> RunResult`

RunResult includes run/task IDs, schema version, execution status, release/environment hashes, ordered event references, outputs, usage, artifacts and structured error. Execution success means the runtime finished normally; it does not assert task correctness.

Separate EvaluationResult includes `pass | fail | invalid_evaluation`, evaluator/dataset hashes, task/attempt IDs, test evidence, policy verdict and integrity state.
- Agent-generated failure, timeout or policy violation: valid score 0.
- Verified hidden-test success with policy compliance: score 1.
- Broken evaluator, missing evidence, corrupted storage or untrustworthy infrastructure: invalid evaluation; block comparison/release. Retry only under an approved bounded policy and preserve every attempt.
- Dependency outages never become successful task results.

### Dataset and feedback
Search 20; validation 10; independent test 20. Keep Smoke for plumbing verification; Smoke never substitutes for release evidence.
Each task includes source fixture, visible tests, protected evaluator tests, allowed files and expected contract. Reject cross-split family/fixture collisions.

GEPA reflection receives only search data: public requirements, permitted source/tool evidence and safe failure categories. Do not expose hidden source, exact hidden inputs/answers, protected paths or secrets. Validation chooses the candidate; independent tests run only after selection freezes. Version and retire repeatedly inspected test sets before broad quality claims.

### Fair comparison and regressions
Freeze workflow, tool policy, model generation settings, dataset, evaluator image, adapter/runtime and empty/frozen memory.
Use matching task/repetition pairs; randomize or balance execution order. Record warmup and provider-reported residency facts without assuming identical cache state.
Primary score: task success rate. Report baseline-pass/candidate-fail cases explicitly. Default release gate: zero newly regressed cases. Secondary criteria: tokens, tool calls and latency under fixed ceilings. Report uncertainty and sample size; three repetitions do not guarantee statistical significance.

### Budget semantics
Separate search task evaluations, validation/final evaluations, reflections, model calls, token allowances, concurrency and wall-time.
The Full GEPA search cap remains 80 task evaluations. Final S0/S1 comparison on 20 tasks repeated three times requires 120 additional task executions. A separate repeated 10-task validation comparison adds 60. Any additional baseline-search work must be explicitly accounted for.
These are task executions, not model requests: each nanobot execution may use multiple requests. Validate and reserve the total budget before dispatch. Cost is unknown when the provider does not report billing; do not invent dollar metrics.

## 8. Required Immutable Release Manifest
- Assets: Skill hashes/versions, workflow hash/version, parent release.
- Runtime: runtime/adapter versions, image digest, exact model identity/available digest and generation settings, approved tools.
- Evaluation: dataset/evaluator hashes, search/validation/independent result IDs and registered gate policy.
- Reproducibility: fixtures, memory snapshot (explicit empty snapshot allowed), supported seeds, execution budgets.
- Governance: approval identity/time/rationale, checksum/signature and key reference.

Keep manifest content immutable. Record approval/activation/rollback as separately auditable records; activation timestamp belongs to the activation event, avoiding changes to signed manifest bytes.
Activate one complete active-release pointer transactionally for new runs. In-flight runs retain frozen manifests. Git manifest publication and database pointer changes require idempotent reconciliation; they are not a single cross-system atomic transaction.
Document key management and verification. Release policy distinguishes a checksum from a cryptographic signature.

## 9. Original Phase Closure and Future Development
### P1–P3 closure after M
Confirm bootstrap/contracts/CI, durable lifecycle/API/GUI, and containerized nanobot/evaluator gates from M. Do not repeat already validated work under renamed steps. Store mappings from original step IDs to StepCheck evidence.

### P4 — GEPA Skill Evolution MVP Closure
| Step | Remaining work and gate |
| --- | --- |
| 4.1 | Finish immutable Skill registry/frontmatter/fixed-field policy tests and provenance links |
| 4.2 | Exercise 80-evaluation search with frozen snapshots and crash/resume accounting |
| 4.3 | Verify safe feedback sanitizer against tool/test/exception leakage |
| 4.4 | Select on validation; execute paired independent comparison and per-task regression/uncertainty report |
| 4.5 | Approve/activate complete signed manifest; prove snapshot preservation and joint rollback |
| 4.6 | Canary healthy/failing cases; provide alert and reviewable rollback recommendation |

GEPA uses the existing real adapter; no replacement with the custom LLM reflection engine. Retaining S0 is a valid outcome. P4 exit requires the complete hardened evidence/release path, not guaranteed improvement.

### P5 — OpenEvolve Workflow Evolution and Attribution
1. Define schema-validated WorkflowSpec with approved roles, DAG edges/order, bounded retries/concurrency, model assignment from a fixed pool and stop conditions.
2. Clarify evolved role prompts versus immutable named Skills. Keep system safety/tool/budget policy fixed; role instructions may vary only in declared workflow fields.
3. Build/test the fixed executor before integrating OpenEvolve.
4. Treat proposed workflows as data: parse, validate and dispatch through the fixed executor. Never execute arbitrary candidate-generated Python.
5. Persist population/checkpoints; enforce mutation boundaries and budget accounting.
6. Freeze S1 while searching W1. Compare S0+W0, S1+W0, S0+W1 and S1+W1 on matched tasks/repetitions.
7. Run final independent gates; release a complete joint bundle or retain the prior release.

Store comparable success/cost/latency and Skill/workflow interaction evidence. Distinguish exploratory attribution data from the final independent set. P5 begins only after P4 release trust is established.

### P6 — Multi-Runtime and Production Operations
1. OpenClaw first: server-side Gateway credentials, approved-skill injection, isolated sessions, separate research/production roots; common contract suite.
2. Compare the same released Skill/evaluator task contract on nanobot/OpenClaw. Report unsupported features and runtime differences; do not claim bitwise reproducibility across engines.
3. Verify actual SDK/runtime capabilities before adding Hermes unique profiles/memory, Herdr observation, and NanoClaw containers/cleanup.
4. Add credential vault, authenticated remote control, RBAC, monitoring, retention/redaction, dependency probes and runbooks.
5. Verify browser-secret absence, cross-run isolation, interrupted cleanup/quarantine and research writes unable to change production assets.

Private hosted GUI access and backend authentication are separate. Preserve the current Site/project identity; inspect source binding before any repository rename-related hosting change. Do not recreate or redeploy the Site just to revise planning documents.

## 10. StepCheck Gates, Recovery and Support Bundles
Each authoritative StepCheck stores phase/step/experiment/candidate/run IDs, command/job, source/dependency/input hashes, start/end/duration, exit code, verdict, artifact references and safe remediation.
Advance only after its gate passes. On failure, block dependent work and preserve the support bundle. Operator acknowledgment alone does not convert failure to pass.

Structured log format:
`timestamp severity debug_code phase step experiment candidate run component message remediation`

| Severity | Behavior |
| --- | --- |
| INFO | Record progress and successful checks |
| WARN | Record degraded condition; retry only under bounded policy |
| ERROR | Fail check; preserve evidence; block dependents |
| CRITICAL | Halt release/experiment, quarantine if required, notify configured operator |

Support bundle: input hashes, runtime/tool versions, redacted stdout/stderr, ordered trace, evaluator verdict, diff/artifact references, usage/time, cleanup state and lineage. Debug logs may rotate; release evidence follows an independent retention policy.

Idempotency covers logical jobs and committed results. External model requests may occur more than once after ambiguous failures; record attempts and uncertainty instead of promising exactly-once external execution. Worker leases/heartbeats and checkpoints reconcile crashed jobs.

## 11. GUI and Delivery Acceptance
Retain current experiment/log/step pages while adding task registry, canonical evaluations, Skill lineage and complete release views. Label search, validation, independent test, baseline, candidate and production explicitly.
Persist events before SSE delivery; reconnect by sequence; evidence DB remains authoritative. Browser closure must not stop real workers. Provide elapsed/activity/deadline states and completed/sent counts across long-running pages.

Required checks:
- Existing quick/model/release commands remain valid during migration.
- Add runnable focused checks for each M gate; the commands must exist before the gate is claimed.
- Pinned SDK integration cannot silently skip missing dependencies.
- Use Playwright for real browser settings, navigation, run progress, reconnect, approval and rollback.
- Documentation-only changes receive link/Markdown/status checks; they do not justify claims of new runtime validation.

## 12. Definition of Done and Immediate Next Action
**Immediate next development:** M-A baseline migration fixtures and canonical contracts, followed by M-B durable evidence and isolated evaluator. User-authored datasets proceed within M5; arbitrary multi-file repair waits for M4 isolation.

**Hardened MVP:** GUI-driven nanobot baselines, bounded GEPA search, safe feedback, independent comparison, per-task regression gates, complete evidence, retain-S0/approve-S1, immutable activation and rollback.

**Complete platform:** P5 workflow evolution/attribution/joint release and P6 validated multi-runtime operations pass.

**Repository transition checklist:**
1. Commit this plan and README navigation under the current repository.
2. Rename the existing repository to agent-evolution-platform; preserve identity, history and visibility.
3. Verify new repository name/URL and actual hosting source binding.
4. Update canonical repository links after successful rename; leave old commit history intact.
5. Existing WSL checkout may remain on D under its current directory. After rename, run:
```bash
cd /mnt/d/nanobot-gepa-mvp
git remote set-url origin https://github.com/edwei-2021/agent-evolution-platform.git
git pull --ff-only
```
6. Do not relocate .local data, reset settings, rerun Windows diagnostics or bump the application version solely for this plan.
