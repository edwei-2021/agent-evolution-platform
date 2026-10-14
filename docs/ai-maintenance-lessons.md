# AI Maintenance Lessons: M7 Failure Recovery

Audience: AI maintainers and human reviewers. Updated: 2026-10-14.

This document records mistakes in the M7 repair process, including the repeated GEPA reviewer timeout, and the concrete rules needed to avoid repeating them. It is a working handoff, not a claim that every target environment has passed. Read it before changing runtime discovery, timing, or release supervision.

## Current finding: reviewer timeout repeated despite a written lesson (再次缺漏)

Evidence supplied in the terminal transcript: outer `MCHECK-217adc0bacc24977bb47f06ca2916115`, nested `CHECK-2e7c23d60d19420997702b39a8f26d33`. Ten GEPA cases passed; `test_perfect_seed_skips_proposals_and_cannot_release_without_improvement` failed after 409.470 seconds with `Workflow time limit exceeded`, with reviewer active and 17 completed rollouts reported. The final optimizer/approval/rollback/tamper case did not execute. The current support ZIP was not attached here. Therefore the precise frozen deadline, reviewer row at termination, and any particular slow I/O operation are **unconfirmed**. The terminal duration includes setup/cleanup and is not itself the workflow deadline.

**Accountability:** the lesson was incomplete in its enforcement. The previous reviewer fix used `60 + total * (7 + 5 * io)` with opaque coefficients. Its `reviewReplays` field was descriptive and did not participate in an independently checkable phase sum. The regression asserted a minimum number of seconds, so it could pass without counting the real work. The native-health fix then proved its own 90/120-second boundaries; that evidence did not qualify GEPA's successful-tool branch or reviewer workload. Asking for another broad acceptance run transferred this unfinished audit to the user.

### Understandable procedure for this failed case (失敗步驟展開)

| Order | Operation | Work that must be counted | Interpretation |
| --- | --- | --- | --- |
| 1 | Freeze the seed, grouped dataset and limits | Smoke: up to 8 search + 12 final rollouts; six requests per rollout, two reflections maximum | Limits are fixed before dispatch |
| 2 | Run search with the perfect-seed model | Successful tasks read, write and run visible tests; four requests each in this fixture | A perfect seed can cost more per rollout than a bad seed that immediately stops |
| 3 | Verify each completed rollout | A fresh trusted subprocess recomputes visible/hidden scores and checks tool evidence | Verification pass 1; model assertions cannot score |
| 4 | Run baseline and selected Skills on final validation/heldout tasks | Both are evaluated even when the selected Skill equals the baseline | Same Skill does not authorize skipping independent final measurements |
| 5 | Evaluator verifies the entire ledger | Replays every rollout with fresh trusted tests | Verification pass 2 |
| 6 | Reviewer independently verifies the entire ledger | Repeats the trusted replay and compares evidence | Verification pass 3; the reported failure occurred in this role |
| 7 | Record completed but ineligible result | Zero proposals and no improvement means release is refused | This assertion was blocked by the timeout |

The code contains three trusted verification passes per rollout, plus the visible-test tool subprocess on a successful repair. The previous formula did not express these separately. It also did not reserve the ten-second request limits multiplied by the actual permitted request count. This is a concrete workload-accounting defect; the supplied transcript does not prove which operation consumed the remaining time on WSL.

### Further defect caught in this requested tail: premature warmup completion (本輪攔下的競態)

The local scoped run `CHECK-d7ca0a4ca6d74970817497323fe8509b` passed 146 cases before reaching the previously unexecuted warmup module. Its first case observed `FAIL` while `operation.locked()` was still true. The old finalizer persisted terminal status **before** writing the final log, deleting temporary request files and releasing the provider slot. This was an event-order defect, not an insufficient wait allowance.

A deterministic event barrier reproduced the same defect on the successful branch: while the final log was paused, `warmup_status()` already returned `PRELOAD_PASS` even though the slot remained owned. The old implementation failed this new case in 0.864 seconds. The repair keeps the record `RUNNING` during log/file cleanup, then serializes terminal persistence and slot release with status reads. Success, timeout failure, cancellation and restart cases are checked. Final logging is outside that brief read/write critical section.

The one-second timeout fixture retains its production limit. Its functional assertions cover the frozen limit, failed status, evidence and at most one request; cold startup may expire before dispatch. A separate controlled-clock case waits for an actual request, advances only the bridge clock past the frozen limit, then proves that the real worker is reaped, the slot is released and exactly one request occurred. Aggregate setup/logging time is no longer confused with the one-second request/workflow deadline.

This widens the shared lesson: a visible milestone is not proof that all required work has finished. Budget accounting must cover verification and cleanup; terminal-state publication must wait for owned-resource cleanup. The original document's timer-focused audit did not enforce this lifecycle contract.

### Common failure pattern and executable prevention (共同核心與防止再犯)

| Common mistake | Why prose alone did not catch it | Required executable check |
| --- | --- | --- |
| Adjust the timer nearest the latest traceback | An enclosing or repeated phase remains outside the count | Sum named phase reserves; assert three verifier batches per actual rollout |
| Treat successful cases as interchangeable | Perfect-seed success exercises more tools and writes than an immediately unsuccessful seed | Inspect the fixture branch; check requests, tools and verification counts on the exact failed case |
| Test that a new timeout exceeds the old number | A threshold assertion mirrors the patch and cannot detect omitted work | Test resource counts, phase sum, invalid calibration, and parent containment |
| Publish completion before cleanup | Fast scheduling hides a terminal-record/provider-slot race | Pause finalization with an event barrier; status stays RUNNING until owned cleanup and slot release complete |
| Stop accounting at workflow completion | Direct verification and approval can replay all evidence again | Reserve four extra replays for direct verify, approve, duplicate approve and final-row tampering |
| Recalibrate independently in parent and child | Different samples produce different frozen limits, even on the same checkout | Pass the parent calibration into every child; assert identical input and parent containment |
| Use one GEPA module timer for multiple workflows | Increasing the inner limit can exceed the unchanged 7200-second parent cap | Expand GEPA into uniquely named exact-case steps; each parent includes workflow, extra replays and cleanup |
| Append generic prechecks to a recovery run | Previously passed frontend/API/harness work gets repeated | Assert exact failed + unexecuted selection and absence of repeated prechecks; retain legacy recovery only for a failure in a legacy harness step |
| Interpret fast Linux success as WSL qualification | Storage calibration measures a limited operation, not every possible host stall | Run controlled slow reviewer execution beyond the observed old failure duration; retain the target-environment qualification limit |

The final plan uses Windows-safe log names and validates every selected GEPA case budget before the first model dispatch. The new manifest separately reserves startup, requests, visible test tools, immediate verification, evaluator replay, reviewer replay and calibrated journal/file work. Request timeout (10 seconds), trusted subprocess timeout (5 seconds), call/proposal/metric limits, independent scoring and approval checks remain enforced. Excessive calibration is rejected before dispatch rather than silently clamped. I/O allowances and startup reserve remain engineering policy, not a mathematical guarantee against arbitrary operating-system stalls; report their assumptions explicitly.

### Unexecuted tail audit (未測步驟檢查)

- Final GEPA case: all three workflow verification passes plus **four** post-completion replays. Duplicate approval verifies before checking the changed baseline; tampering in the last row can replay the entire ledger before rejection. Preserve these checks.
- Later release modules: execute only modules following GEPA in current discovery order. Native runtime health expands its five-module frozen plan with existing 30/35/50/60-second cleanup containment. Previously repaired SDK discovery, startup, transport and cancellation guards remain in place.
- M7 final checks: Ruff and strict TypeScript follow the release tail. The source scan is a directly affected guard for the changed `platform_m/gates.py`; its earlier pass is not presented as an unexecuted step. Previously passed frontend and M7 API/gate prechecks are omitted from strict continuation.
- New or changed supervision logic requires its own focused regressions. That does not authorize repeating the ten passed GEPA integration cases or M1–M6.
- Current input is a pasted terminal anchor, not an uploaded support archive. `--from-case` records that distinction; never fabricate an archive hash or claim its contents were inspected. Prefer `--previous-support` when the actual ZIP is available.

Local verification results for this revision are recorded in `docs/m7-reviewer-followup.md`. They do not certify WSL or full phase M acceptance.

## Previous finding: missed native workflow deadline (前次缺漏)

The 2026-10-14 follow-up is M check `MCHECK-9d3e8d24d8ec4c32b0e20117489abc72`, nested release `CHECK-7ec86c9c4b0745d4aa0d25f33ec57cf0`, source `8a67a257ab90d6c8852518787b690f0ed6e243cc90b57af48d7f411362a01d0e`. Its relevant source files match the published repair. LLM passed 17/17, repair 12/12, and the first nine runtime cases passed. The tenth runtime case failed; three later runtime cases and eight later modules remained unexecuted.

The previous audit missed `runtime_test → RuntimeService → native_agents evaluator → unittest discover s*_test.py`. The evaluator still used `subprocess.run(timeout=90)` to run five modules, while its native parent still enforced a 120-second role limit. The case's outer completion allowance did not change either inner limit. The 90-second child timer fired; the evaluator exited 1; the runtime assertion then failed. This is an audit and implementation omission. The previous local 13/13 result did not exercise a child beyond these old deadlines.

| Step | Observed outcome | Meaning |
| --- | --- | --- |
| Asset inspection | Completed, about 1.2 seconds | Source/assets were readable |
| JavaScript checks | Completed, about 3.9 seconds; 95 passed | Frontend checks passed |
| Native Python evaluator | Stopped after about 91.2 seconds, including timeout handling | Its fixed 90-second subprocess limit fired |
| Reflection and review | Skipped | Failed evaluator blocked dependent roles |
| Runtime integration assertion | Failed after 102.724 seconds | Expected completed workflow; received failed status |

The uploaded ZIP contains the evaluator traceback but omits its temporary `python-tests.log`. It cannot establish which nested Python case was active or whether it would eventually pass. Do not invent a failing inner test or claim that a model or SDK defect caused this timeout.

The old `s*_test.py` expanded to `sdk_runtime_probe_test.py`, `setup_orchestrator_test.py`, `setup_test.py`, `skill_test.py`, and `step_trace_test.py`: 60 cases. This repair retains those five modules explicitly, runs them separately with case progress, rejects missing/skipped/non-passing case records even on zero process exit, and freezes scope, source hashes, calibration, per-module bounds and native role limits before dispatch. The native parent and runtime test consume the frozen plan. Native child cleanup, role cleanup, module cleanup and M parent cleanup are ordered at 30/35/50/60 seconds. The Skill completion helper also used an unrelated 15-second polling wait; it now follows terminal persistence within the existing role budget.

The remaining SDK timeout fixture also assumed metadata/import startup completed within 0.5 seconds. Its import-phase test now uses a controlled clock after observing import, with a deliberately delayed 0.7-second startup. A separate real-time test verifies that the whole-probe deadline still includes startup. The production SDK deadline is unchanged. The original 60 native cases are retained; this added startup regression brings the manifest to 61 cases.

Native failures preserve the temporary run's JSON/log files before cleanup, including each nested module log and active-module report. Both the full M archive and the scoped continuation archive include bounded, redacted `failure-evidence/` content, reject artifact symlinks, and record size-limit omissions. Full M failure output prints an exact `M7_RECOVERY_COMMAND` only when a valid failed Python release case is present. That command resumes the failed runtime case, its three successors, and later checks without repeating GEPA/LLM/repair.

For this uploaded failure, the target checkout's existing report can be used directly after updating the source:

```bash
.venv-m/bin/python scripts/check_m7_remaining.py \
  --previous-support .local/m/support/MCHECK-9d3e8d24d8ec4c32b0e20117489abc72/support.zip
```

This is a scoped continuation command; it does not start M1–M6 or repeat completed GEPA/LLM/repair modules.

### Required evidence before the next handoff (交付前必備證據)

1. Enumerate every nested `subprocess.run`, `Popen`, role launcher, unittest/pytest selector and wildcard reachable from the affected integration case. Record leaf commands and scope counts.
2. Show each command's execution allowance, its parent allowance, termination grace and report destination. Freeze planned work before dispatch; preserve intentionally short timeout fixtures.
3. Exercise slow execution past both former limits. A local fast pass alone cannot close this audit item. Verify the production parent reads the new plan.
4. Fault-inject a child failure and timeout. Verify fail-fast behavior, process-group termination, exact leaf evidence and archive contents after temporary-directory cleanup.
5. Reject an incomplete audit ledger. A module-level pass must not be labeled as an inspected subprocess graph. Scope changes and renamed test files require renewed inventory.

### Follow-up verification (本次驗證)

- The original native integration case passed locally in 29.435 seconds before the final fixture refinement; the complete runtime module was then rerun and passed 13/13 after that refinement, including the actual native workflow and all 61 nested native cases.
- A real controlled child slept for 121 seconds. It ran through the native subprocess supervisor and the production runtime role supervisor, crossed both former 90/120-second limits, and completed with five successful roles in 122.264 seconds. The controlled child had a 150-second declared limit; its parent consumed the frozen plan rather than the old 120-second role limit. No model requests were sent. This is a latency fault experiment, not a WSL acceptance result.
- Scoped recovery `CHECK-f3189da5fc59457ca3123a10db01c72c` completed 18 steps and recorded 109 successful unittest case results, plus 23 M7 API/gate pytest cases and 95 frontend tests. It began with the failed runtime case and included its three successors, eight later modules, native/monitor/selection regressions, source scan, Ruff and strict TypeScript. GEPA, LLM, repair and M1–M6 were omitted explicitly, with historical evidence retained.
- Native scope/deadline/cleanup/failure-export regressions passed 7/7, including rejection of a zero exit code with missing case evidence. The final SDK probe module passed 13/13. The full M archive regression verifies deep native logs, redaction and a valid recovery command. Source and fixture refinements made during local review were followed by targeted reruns; the scoped report identifies its own source snapshot rather than claiming final-source whole-phase acceptance.

The uploaded WSL archive does not establish an underlying Python assertion failure inside the old evaluator, because its inner log was lost. Completion on the edited source still requires target-environment evidence. The engineering omission is addressed with an explicit manifest, consumed bounds, slow-execution proof and retained leaf evidence; a new fast local result alone would not suffice.

## Previous evidence and accountability

The preceding uploaded evidence is M check `MCHECK-b6eebef0e2a647a08909a5159294a81c`, nested release check `CHECK-4622ea9f9cbb4ddfbdf4e7e0a61d0ce0`, source hash `be893d28e6b22d0bb645bac81b489a1063f12b2a351d06480feda445fdc124de`. M1–M6 and M7's four initial checks passed on that source. The release check reached `python-llm_test` after GEPA passed 12/12 with zero skips in 1904.618 seconds. The LLM module failed after 354.680 seconds; eight cases passed, the ninth errored, and eight remained unexecuted. Exit code 1 indicates a test error, not the monitor's hard-limit exit 124.

Earlier incident details below come from the troubleshooting record and previous fixes in this repository. Do not imply that the latest support ZIP contains all earlier incidents. The maintenance mistakes included treating fast local success as sufficient, adjusting one timer without tracing its callers, and asking for broad reruns before auditing the remaining tail. The user bore the cost of those omissions.

## Incident register (錯誤與預防對照)

| Mistake / incident | Cause | Prevention rule | Required proof |
| --- | --- | --- | --- |
| WSL pytest capture/rename failed before assertions | Pytest FD capture used unstable DrvFS temporary files; a Linux rename assumption was applied to a mounted Windows filesystem | Preserve `pytest -s` under the outer log collector; place rename-only fixtures on the native Linux filesystem | Run capture-free M commands and the separate verified-copy fixture; do not reinterpret infrastructure errors as assertions |
| A five-second functional assertion measured startup, call timeout, storage, and cleanup together | The WSL case took 8.65 seconds even though the one-second model deadline was enforced | Assert frozen timeout, failed terminal evidence, exactly one request, and released slot; test deadline arithmetic separately with a controlled clock | Do not equate total case duration with the model-call timer |
| Full LLM validation stopped at 43 of 101 calls under a fixed 60-second budget | Fast 13–22 ms model responses hid cumulative storage/orchestration cost | Calibrate journal and atomic writes on the actual checkout; freeze workload-derived smoke/full budgets before dispatch | Reject invalid/excessive calibration rather than extending a running workflow |
| SIGSEGV (-11) was easily confused with a shell-wrapped exit code 245 or a timeout | Native crash classification and diagnostic retention were insufficient; correlation with a former 25-second watchdog did not prove cause | Preserve original signal, fatal trace, environment, thread/state samples and a stable wrapper code; do not auto-retry | Fault-inject signal handling; state that the original native root cause remains unconfirmed |
| JavaScript subprocess limited to 90 seconds while GEPA work could exceed 120 seconds | An outer test timer ignored serial search, final evaluation, and cleanup | Calculate the entire enclosed workload before choosing its outer limit | Show the serial call counts and frozen budgets; test the outer timeout path |
| Independent reviewer replay was omitted from the workflow budget | The evaluator passed, but replay of 18 evaluations still required time; a 279-second workflow could stop during review | Include all independent verification, not only candidate generation and selection | Confirm the reviewer has budget after evaluator completion; preserve exact call accounting |
| A module estimate treated a 12-case GEPA module as one workflow | Case, workflow, and module estimates were conflated | Sum complete workflows and smaller cases separately | Compare per-case timings with the module estimate; keep estimates separate from enforcement |
| Fixed first-request waits of 15/10/5 seconds misclassified slow startup | WSL interpreter/import and filesystem work occurred before any model request | Observe startup and dispatch separately, with a bounded calibrated startup allowance | Verify whether the mock server received a request before calling it a model timeout |
| A fixed 10-second SDK probe reported an unavailable package after about 10.56 seconds | Slow import was collapsed into missing-package status; failed discovery could remain cached | Use staged, bounded discovery and distinct missing/version/import/timeout/launch errors; never use negative observations to suppress a dispatch probe | Slow real import, missing package, wrong version, import crash, native exit, timeout kill, recovery after failure |
| A nested wait prompt appeared without a newline; blocking stdin stopped supervision | Parent output was line-based; the child stopped draining output and checking deadlines while asking a question | Flush complete progress lines; poll interactive input without blocking; disable prompts in unattended child checks | Child completion is observed while stdin remains open; hard deadline still terminates a waiting child |
| A two-hour outer cap covered many individually bounded modules | The wrapper timer represented the whole release, while child limits represented each step | Supervise authenticated sequential step transitions, heartbeat, startup, and cleanup independently | Reject foreign/duplicate/invalid control frames; prove silent/stuck children remain bounded |
| Latest LLM GET failed before submission | `/api/v1/llm/skills` built a full runtime snapshot that synchronously probed unrelated SDKs; nanobot import took 5.694 seconds while HTTP allowed 5 | State reads must not import optional SDKs synchronously. Cold and expired caches are normal operating states | Hold discovery pending while real HTTP reads finish; verify availability only after discovery completes |
| Remaining runtime API cases had the same latent dependency | `/runtime` and `/capabilities` used the same discovery path; fixing only the first LLM route would move the failure downstream | Trace shared callees across all remaining cases and approval/rollback paths | Exercise capabilities, runtime, LLM, rule skills, repair, and GEPA reads with discovery blocked |
| Native runtime audit missed the evaluator's five-module wildcard and 90/120-second inner limits | The review stopped at the runtime test helper and did not expand its subprocess graph; fast local execution hid the mismatch | Freeze an explicit leaf manifest and shared deadline hierarchy; run a child past the former limits | 121-second controlled nested execution, real native integration, cleanup and recursive archive regressions |
| Repeated broad user reruns discovered independent problems one at a time | There was no exact case/tail runner or explicit scope ledger | Run the failed leaf locally, audit its successors, then execute a scoped tail with recorded omissions | Reject unknown/empty selection; preserve prior report identity and the changed source manifest; do not call a tail pass a full M pass |

## Previous HTTP failure as an understandable procedure (作業流程)

| Step | Operation | Expected result | What actually happened / correction |
| --- | --- | --- | --- |
| 1 | Start a loopback HTTP server using a new local runtime | Server listens; no model calls | Completed |
| 2 | GET `/api/v1/llm/skills` | Read baseline `LSV-baseline` | Failed here before this repair |
| 3 | Build the response from stored state | A read should not depend on nanobot/GEPA imports | Old code built every workspace and launched SDK discovery synchronously |
| 4 | Wait for the HTTP response | Five-second client limit | SDK probe alone took 5.694 seconds, so the client disconnected first |
| 5 | Reject a submission without a valid session token | HTTP 403 | Previously unexecuted in this case; now verified |
| 6 | Submit the valid LLM workflow and await its terminal state | Recorded model calls, independent evaluation and review | Previously unexecuted in this case; now verified |
| 7 | Read `/api/v1/runtime` and check history | Correct latest run | The same latent SDK coupling existed here; now reads observed readiness immediately |
| 8 | Approve the eligible version | Active version becomes `L1` with a revision change | Now verified |
| 9 | Activate the baseline | Active version returns to `LSV-baseline` | Now verified |

A controlled reproduction before the repair held SDK discovery for six seconds: the old GET timed out at 5.008 seconds, while the direct LLM store read took about 0.0003 seconds. That establishes unnecessary discovery work in the response path as the cause. A successful SDK result after the client disconnects does not make the HTTP request successful. The server-side follow-on exception's exact type was not retained; do not invent it.

## Runtime rules after this repair

- `package_status(..., cached_only=True)` observes a serialized result without starting a subprocess. A missing current observation has `available: false` and `errorCode: not_probed` (尚未完成偵測), not a fabricated installed result.
- Observations use the same interpreter, installation marker, interpreter timestamp, and five-minute window as positive probe caching. Changed or expired identities become unknown immediately. Failed observations can be displayed, but direct discovery and dispatch retry the actual probe rather than treating that observation as a reusable failure result.
- Runtime reads schedule at most one background discovery per service/interpreter-identity/window, with no workflow mutex held. SDK and GEPA imports retain their existing 120-second per-probe bounds. Reading, polling, or obtaining a CSRF token does not consume the model operation slot.
- SDK submission preflight also runs outside the workflow mutex: otherwise an expired import during submission could block every state read behind that lock. Admission/idempotency and GEPA revision are rechecked after preflight; provider revision is rechecked after leasing the model slot. Failed preparation allocates no run or model slot. An event-gated HTTP regression proves reads stay available during blocked preparation, and a revision-race test prevents stale dispatch.
- GEPA state/version reads use observations. GEPA configuration freezing explicitly probes pinned dependencies. Repair freezing keeps its real pinned probe. Version, revision, approval, evidence-integrity, model-call, and workflow gates remain enforced.
- SDK submission HTTP deadlines cover explicit revalidation at a cache-window boundary: repair allows one 120-second probe plus 30 seconds of response/dispatch grace; GEPA allows two probes plus 30 seconds. The adapter tests explicitly establish SDK readiness before submitting; a first asynchronous status response is allowed to be pending. These are submission-only bounds; state-read HTTP limits and frozen model/workflow limits are unchanged. GEPA reuses the nanobot result for its optimizer check, avoiding a duplicate failed SDK probe.
- The UI labels pending discovery as `偵測中，請稍候`; action buttons remain disabled until readiness is confirmed. Polling updates live readiness even though session capabilities are fetched once.
- Background discovery is bounded optional environment work; a read response does not wait for its completion. It does not submit model requests. A failed observation remains visible for its current window; a direct dispatch check still performs its required probe.

## Timing model (逾時層級)

| Boundary | Work that belongs inside it | Maintenance rule |
| --- | --- | --- |
| State-read HTTP | Database and recorded progress reads | Keep unrelated imports and inference out of this path; retain the five-second regression client |
| SDK discovery | Interpreter startup, metadata, exact-version validation, import | One absolute deadline and staged diagnostics; no model calls |
| Model call | Transport, streamed chunks, terminal response | An absolute deadline must not be renewed by partial chunks; no hidden retries |
| Workflow | Coordinator, worker, reflection, evaluation, independent review | Derive serial workload and preserve the frozen whole-run limit |
| Test case | Setup, workflow, assertions, cancellation, teardown | Distinguish a functional result from a deliberate short timeout fixture |
| Module | Every selected case | Sum work; fail at the first failure; record omitted and executed IDs |
| Parent monitor | Child startup, authenticated step deadlines, heartbeat, cleanup | Never block deadline enforcement on stdin or an output prompt |

Do not inflate every `timeout=5`, `wait(5)`, or fixture delay. Some intentionally test cancellation or an absolute transport deadline. Identify the actual owner and enclosed work first. Human `normalSeconds` estimates describe expected duration; hard limits enforce bounds and must remain active after progress or prompts.

## Mandatory workflow for the next AI (接手程序)

1. Read the first failed leaf's traceback and final per-case record. Record source hash, report IDs, exit code, and last observed stage. Separate assertion failure, HTTP timeout, model timeout, workflow deadline, native crash, and interruption.
2. Trace both the direct callee and shared paths used by subsequent cases. Inspect snapshot construction, cache keys/expiry, broad exception handling, subprocess trees, stdin, and deadline ownership.
3. Write a deterministic local reproduction using the observed failure boundary. For latency faults, use an event gate or slow isolated import. Do not rely on machine speed to make the test fail.
4. State the invariant being restored. Prefer removing unrelated work from a read over raising its timeout. Preserve exact versions, authorization, evidence checks, independent review, and intentional timeout fixtures.
5. Audit every unexecuted module for the same pattern before asking for target testing. Document why similar-looking timers are either relevant or intentional.
6. Honor the requested scope: run the failed case and unexecuted tail. Verify shared-code changes with focused contract regressions; do not default to repeating earlier passed integration workflows. Any additional check must directly exercise the repair. Inspect skips and subprocess exit codes rather than only the last `OK` line.
7. Review the full diff and publish the tested change with an exact scope statement. Existing publication authorization should not be repeatedly requested.
8. A local Linux result is evidence for that environment. Do not claim target WSL acceptance, Docker acceptance, unchanged-source continuity, or a full M7 pass without corresponding evidence. Do not ask the user to repeat 31 minutes of already completed GEPA checks merely to reach the next independent failure.

## M7 continuation usage (失敗後接續驗證)

From the checkout root, after pulling the repair and installing the repository's existing dependencies:

```bash
.venv-m/bin/python scripts/check_m7_remaining.py \
  --previous-support /absolute/path/to/previous/support.zip
```

The input can also be the nested failed `release/report.json`, or a failed continuation report/ZIP. A second failure resumes at its failed case or static check without repeating completed model modules; commands are reconstructed from current source rather than replayed from report data. The runner reads the ZIP report directly and never extracts paths from it. An initial release resume requires a failed Python module and an unambiguous failed/error case preceded by passed case records. A scoped continuation may also resume a failed non-unittest check without inventing case records. Missing anchors fail; they never produce a zero-test pass.

The runner checks the M environment and TypeScript dependency before starting expensive tests. Legacy workflows use `.venv-nanobot`; M API/gate and Ruff checks use `.venv-m`, with pytest capture disabled (`-s`) as required on WSL DrvFS. A local integration attempt caught the initial mistake of using the SDK interpreter for M API tests (`fastapi` was absent); environment routing and preflight were corrected before publication.

The plan performs fresh filesystem calibration, the failed case and its remaining module cases, all later release modules, monitor/selection regressions, frontend checks, M7 API/gate tests, the source scan, Ruff, and strict generated-contract TypeScript checking. It preserves logs, case IDs/timings, the prior artifact SHA-256, source manifest, planned steps, omitted release steps, and a support ZIP. It uses bounded unattended supervision and stops at the first failure. Each invocation reserves its own validated report ID and archives only that directory. A concurrent local integration run exposed that scanning for all newly created reports could select another run; the final implementation uses the reserved ID and tests archive isolation/redaction.

The result is explicitly `m7-remaining`, with `fullM7Acceptance: false` and `fullMAcceptance: false`. Prior passed steps are historical evidence (歷史證據), not re-certified results for edited code. This does not weaken or replace the full release gate.

For an exact local diagnostic:

```bash
.venv-nanobot/bin/python scripts/run_test_module.py llm_test.py \
  --case llm_test.LlmWorkflowTests.test_local_http_submission_history_approval_and_rollback
```

`--from-case` runs that exact ID and its successors in unittest discovery order. Both modes print discovered, selected, and omitted IDs. Listing a selected ID is planning evidence; only `TEST_CASE_STARTED` and `TEST_CASE_RESULT` establish execution. A legacy fail-fast assertion initially searched all output for a later case name and therefore failed on the new selection metadata; it was corrected to inspect actual started-case records, preserving the original fail-fast invariant. They retain fail-fast behavior and the existing SIGTERM cleanup path.

## Remaining-case audit and verification record

The uploaded failure left eight LLM cases, 13 subsequent legacy modules, and the final Ruff/TypeScript checks unexecuted. The new selection regression module also belongs to the tail.

| Remaining area | Risk checked | Proof required / executed locally |
| --- | --- | --- |
| LLM no-gain, provider errors, reflection validation, silent calls, streaming, tampering, whole-run deadline, protocol | Misclassified timeouts, hidden retries, evidence or version bypass | Full 17-case LLM module; original failing case separately |
| `llm_transport_test`, `ollama_test` | Transport deadline vs HTTP state-read deadline | Real loopback transport, error and streaming regressions |
| `polling_boundary_test`, `runtime_test`, `skill_test` | Slow reads holding workflow locks; same five-second API coupling | All module cases, plus SDK discovery held pending across six read routes |
| `repair_test` | Cold SDK dependency, tools, independent scoring, cancel, single-call enforcement | Real pinned SDK workflows; explicit SDK preflight for JS adapter tests (repair and GEPA); pending UI state tested separately |
| `sdk_runtime_probe_test` | Cold/warm/expired/changed cache, wrong version, import crash, timeout, native exit | Real slow import and process cleanup; observation-cache identity regression |
| `setup_orchestrator_test`, `setup_test` | Blocked stdin, cleanup, false setup success | Existing real process and installer regressions; intentional fixture waits preserved |
| `step_trace_test`, `trace_journal_reuse_test` | Tool/test limits, journal identity, tampering | Existing controlled batch/evidence regressions |
| `validation_wait_test`, `warmup_test` | Startup vs model readiness; bounded warmup and cancellation | Existing calibrated wait and warmup regressions |
| Continuation and monitor | Missing/ambiguous anchor, empty selection, skipped upstream work, failure evidence | Exact/tail selection, JSON/ZIP provenance, real runner interruption/cleanup and report regressions |
| Final integration checks | Source credentials, frontend pending state, M7 API behavior, lint and generated contracts | Source scan, frontend tests, M7 unit/gate tests, Ruff and strict TypeScript |

Verification counts and report identifiers follow below. The user's WSL machine has not executed this edited source during this maintenance session.


### Prior revision local results (前次本地驗證結果)

The complete scoped continuation run `CHECK-66166c391d624e8c913e8d0ef2aafd8d` completed all 22 planned steps. It recorded 148 successful unittest case results (127 in the selected legacy/selection tail and 21 monitor cases), plus 23 M7 pytest cases and 95 frontend tests. There were no skips in these case sets. Source scanning, Ruff, generated-contract checking, and strict TypeScript checking passed. The eight previously unexecuted LLM cases and all 13 original successor modules were exercised; the failing LLM HTTP case also passed independently.

The subsequent admission-lock audit added two runtime regressions and moved explicit SDK preparation outside the runtime mutex. After that final runtime change, the affected workflows were revalidated as follows; counts overlap the continuation run and must not be summed as unique coverage.

| Final affected suite | Result | What it establishes |
| --- | --- | --- |
| Runtime / HTTP | 13 passed, zero skips | Cold discovery, six read routes, interpreter-identity change, blocked submission preparation, stale GEPA revision, real processes and admission rules |
| LLM | 17 passed, zero skips | Full module including the original HTTP failure, review, approval, rollback, cancellation, streaming and absolute deadlines |
| Rule skills | 13 passed, zero skips | Existing state, revision, workflow and version behavior after admission refactoring |
| Real nanobot repair | 12 passed, zero skips | Actual pinned SDK tools, JS API client, independent evidence, cancellation and bounded calls |
| Real GEPA JS/API case | 1 passed, zero skips | Actual optimizer dispatch, progress, terminal evidence and client result validation after the shared API/admission changes |
| Selection / continuation | 8 passed, zero skips | Exact and tail selection, historical provenance, later static-check resume, empty/unknown rejection, archive isolation and redaction |
| Frontend | 95 passed, zero skips | Existing clients plus pending readiness and submission-abort bounds without hidden retries |

The final diff also passed Ruff, the source credential-pattern scan, generated-contract consistency, strict TypeScript checking, and whitespace/error checks. The prior WSL GEPA 12/12 result remains historical evidence for its recorded source; this maintenance run did not repeat every completed GEPA workflow or M1–M6. Local loopback tests use real pinned SDKs and controlled model servers. They do not certify the edited source on the user's WSL machine, the Windows model endpoint, Docker, or full phase M acceptance.

## Start-menu handoff rules (起始選單交付規則)

Manual stage/step selection must preserve original indices and explicit omissions. A partial pass cannot populate complete-stage acceptance history. Cancelled/empty input must never trigger full execution. For M7 release, select module and case from current source before dispatch; retain required calibration, SDK validation, exact-case GEPA bounds and downstream failure blocking. See [the start-menu guide](m-check-start-menu.md).

Executable identity must come from the command's interpreter/script position. Searching the entire argument list misclassified Ruff because it includes `scripts/check_steps.py` as a lint target. Validate the selected child manifest against the same source-owned release tail used by execution. Keep menu prompting separate from unattended child supervision and explicitly disable it in CI/setup.
