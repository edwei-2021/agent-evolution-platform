# Bounded GEPA task failures (單題失敗與整輪評測)

## Observed boundary (觀察到的失敗步驟)

The supplied bank experiment made real model requests and completed ten rollouts before failing on the next selected-Skill decimal-parser task. The baseline public tests passed one of three cases. Repeated source replacements were rejected for unavailable calls, oversized/nonfinite constants, module statements/imports and power syntax. The task consumed its ten requests, the native SDK reported `max_iterations`, and the exception stopped final evaluation before the remaining held-out tasks and reviewer.

The whole workflow and global model budgets were still available. This was a local task-cap failure following repeated policy rejection. The body-free archive does not identify the exact unsupported callee or contain the attempted source; do not invent either. The historical experiment remains failed.

## Missing contracts and corrections (缺漏與修正)

The task prompt previously referred to approved builtins/methods without enumerating them. Call rejection also mentioned recursion even when the unavailable construct could be an ordinary method. Bank prompts and rejection feedback now derive the exact names from the same allowlists used by the evaluator. Feedback names the rejected call/attribute and line, without copying source literals. It also states finite literal bounds, forbidden power syntax, helper-function/comprehension restrictions and accepted exception forms. The accepted AST subset is unchanged.

The second gap was treating an agent's inability to finish one challenge as infrastructure failure for the entire bank experiment. New bank configurations freeze `bounded-task-cap-zero-v1`. Standalone repair and legacy Smoke/Full retain strict SDK-failure behavior.

For the bank, only a native `max_iterations` result with no SDK error can qualify for a failed-task score. The recorded request count must exactly equal the frozen per-task cap; every HTTP/model request must have completed within the workflow deadline, and the last response must still request tools. No summary-mode request or failed evaluator tool can qualify. Runtime collection also checks that the workflow has not expired. Cancellation, failed requests, expired deadlines, evaluator failures, invalid source/evidence and unexpected stop reasons remain fatal.

The worker freezes the unchanged or last accepted source and raises a distinct task-cap exception. The GEPA adapter catches only that exception. Immediate verification reconstructs the granted tools, successful source writes, request parameters and test evidence, and independently evaluates public and hidden cases. It records `taskOutcome=call-limit`, preserves `sdkStopReason=max_iterations` and sets `repairPassed=false`, even if the final source happens to pass every case. Evaluator and reviewer replay the same evidence. A native SDK failure is never relabeled successful repair.

The optimizer receives a zero score and failure feedback for an exhausted training task. Baseline/selected final tasks follow the same policy, and later tasks still run. Final results list each exhausted rollout separately from trusted success totals. Release eligibility still requires a changed Skill, strict validation improvement and no held-out regression; completing the aggregate measurement alone is insufficient.

No calls are retried and no budget/deadline is increased. A cap's native finalization attempt remains blocked before HTTP dispatch. Historical runs and already frozen requests are not resumed or rewritten.

## Later-stage journal ownership (後續階段紀錄歸屬)

A normal integration check also caught a global journal missing the last rollout's four model records, despite those records existing in its child evidence. An isolated rerun passed. A controlled regression establishes that publishing an earlier runner after a newer runner can truncate the newer call suffix under the previous implementation.

Global publication now holds the session's lock and refuses a preceding runner's shorter suffix once a later runner has published. It preserves the later call projection and complete global accounting. Child evidence remains separate, and the reviewer continues to reject missing or inconsistent records instead of reconstructing success silently. A delayed earlier publication is explicitly tested after a subsequent rollout.

## Execution graph and focused proof (執行圖與驗證範圍)

The real pinned SDK fixtures run coordinator → native GEPA search → training reflection → frozen selection → independent baseline/selected validation and held-out tasks → evaluator replay → reviewer replay → approval verification. Model servers are scripted loopback fixtures, not Windows/GPU experiments.

The bank test ceiling is 22 rollouts, six requests/task plus one proposal (133 requests), at most 24 visible-test tools/task and three independent five-second verifier batches/task (66 batches). Its 4450-second workflow bound includes startup, serial ten-second requests, bounded tools, all verification and cleanup; terminal collection adds 30 seconds. Trusted evaluator subprocesses retain their five-second bounds. No M7 selection or production timeout changed.

Focused cases cover:

- Policy rejection and cap exhaustion during search, baseline, selected validation and selected held-out evaluation, with remaining final tasks and review completed.
- Training reflection receiving the failed task outcome; zero-score counts agreeing across final totals, topic/difficulty breakdown and the shipped JavaScript validator/view.
- A correct last-call source scoring zero because the SDK did not finish, plus rejection of a forged completed stop reason.
- One HTTP failure aborting without retry, zero-score substitution or final-data access; shared-provider release after terminal persistence.
- Classification rejecting cancellation, incomplete caps, failed calls, expired completion, summary-mode requests and failed test tools.
- Complete normal search/review/approval after a live bank edit, legacy strict task caps, perfect-seed ineligibility and summary/hidden-regression behavior.
- The staged isolated evaluator's twelve reference oracles and exact source-policy feedback, without changing accepted syntax.

The sidebar separately gains desktop vertical overflow and nonshrinking children so all WORKSPACE entries remain reachable. Mobile horizontal navigation remains under its existing media rule. No browser executable is available in this verification environment; CSS structure is reviewed, without claiming browser visual qualification.

## Maintenance rule (維護規則)

Follow the first rejected tool before changing model choice or raising iteration limits. Keep model-facing grammar synchronized with the executable policy. Distinguish task inability, native turn completion, trusted source correctness, transport and aggregate experiment completion. A zero score needs replayable evidence; it is not a generic exception fallback. Test the unexecuted final tail and approval path with actual bounded SDK processes, and protect later journal records from stale publications.
