# Bounded repair completion contract (修復流程結束契約)

Follow-up: [bank-only failed-task scoring](gepa-task-failure-followup.md) preserves `max_iterations` as a native failure and never promotes it to successful repair. A new frozen policy lets GEPA measure such a task as zero and continue remaining bank evaluations; standalone repair and legacy profiles retain the strict failure behavior described here.

The real Strata API and preload succeeded. In the supplied repair trace, the worker read the baseline, measured failing visible tests, wrote a valid repair, and reached a full visible pass on request four. The exact tool result was present in the next request. It then read the unchanged solution and repeatedly reran already passing tests. A later response announced a summary while also requesting another test. Eight requests completed successfully, but no tool-free terminal answer arrived before the frozen cap. The native SDK reported `max_iterations`; its attempted extra finalization request was blocked before HTTP dispatch.

An offline independent evaluation of the supplied candidate passed both visible and hidden splits. That establishes candidate correctness for this fixture only. The historical run remains failed: its evaluator and reviewer never ran. Private identifiers, provider configuration, uploaded payloads and attachment hashes are excluded from this document.

## Cause and shared lesson (原因與共同缺漏)

The model could repair the function and receive valid tool results, but did not stop choosing tools. The application exposed the same tool set after visible completion and depended on an unforced text summary to finish the SDK turn. The earlier compatibility diagnostic proved one synthetic tool exchange, while scripted workflow models voluntarily returned a final answer. Those tests did not exercise a model that keeps asking for tests after success.

The recurring maintenance error is treating a successful intermediate milestone as proof of the next lifecycle transition. More passing API tests, longer deadlines, larger iteration limits or written reminders do not prove tool-loop termination. Define who owns the transition, what evidence authorizes it, and what the downstream reviewer can independently check. Distinguish function repair quality, tool-selection/termination behavior, transport and orchestration before attributing an entire failure to model quality.

## Implemented transition (實作方式)

`visible-pass-summary-v1` is frozen in repair provenance. A completed trusted visible-test result authorizes summary only when it passes a nonempty test set and the hash of the source actually submitted to the evaluator matches the current file. A concurrent file replacement during testing cannot qualify the replacement. A changed source reopens the tool phase. Failed tests, missing evidence and failed test tools do not authorize summary.

The next ordinary model request uses an empty tool definition list and a fixed summary-only instruction. Strata additionally receives `tool_choice="none"`; the reviewed server implements it. Ollama receives no unsupported tool-choice field. Both paths reject a returned tool call, a truncated answer or a missing/empty final answer. This request counts against the existing cap and deadline. A pass on the last permitted call does not authorize an extra request. Native SDK completion is still required; `max_iterations` is never converted to success.

Independent verification replays tool/source identity and the phase decision, requires the exact summary instruction and provider-specific wire policy, and reruns visible/hidden evaluation. A visible-only overfit can complete the tool phase while still failing the repair result. GEPA release eligibility, approval and rollback remain separate gates. Reflection requests remain separate from summary requests even though both may have no tools.

References: [reviewed Strata handler](https://github.com/edwei-2021/Strata/blob/61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406/serve/server.py), [Ollama supported OpenAI fields](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx). The latter lists `tool_choice` as unsupported at review time; removing tool definitions avoids depending on it.

## Diagnostic gap closed (補足診斷資訊)

Future tool events record source identity and visible passed/total counts. Model-call events identify summary mode, finish reason, requested tool names and output limit. SDK completion records its native stop reason. The existing read-only diagnostic ZIP also projects those fields from bounded existing repair artifacts, so older failed runs can be inspected without dispatching another model call.

The export includes no prompts, source code, full model replies or SDK transcript. Each projection is validated, bounded and sanitized independently before attachment to the status document, preserving useful fields through the redaction depth cap. Tests inspect the actual ZIP consumer, not only the projection helper. Original request/response artifacts remain local and are never overwritten by export.

## Focused validation and execution graph (驗證範圍)

The selected modules are `repair_completion_test`, `repair_test`, `strata_workflow_test`, the exact GEPA perfect-seed case, `tests_m/test_nanobot_bridge.py`, and `diagnostics_test`. No M7 selection, wildcard release manifest or production budget changed.

Real pinned SDK cases expand through the coordinator, worker/native SDK, loopback HTTP transport, granted tools, isolated evaluator (`python -I -S scripts/repair_evaluator.py`), reflector, evaluator and reviewer. GEPA adds the real optimizer, rollout verification, final evaluation and approval/tamper replays. Trusted evaluator subprocesses retain five-second bounds. The fixtures retain their source-owned calibrated workflow limits, ten-second model-call bounds and existing 15/30-second cleanup grace; new repetition fixtures retain eight calls, or two for the negative cap case. The M adapter retains its frozen workflow timeout and uses the actual SDK worker; Docker execution is not part of that adapter test. No request is added after a cap, cancellation or expiry.

The regression set covers repeated successful tests, state mutation, summary instruction/tool-policy tampering, server noncompliance, truncated summary, hidden regression, unchanged absolute caps, cancellation, independent replay, Strata authentication/SSE, GEPA perfect-seed ineligibility, approval/rollback and diagnostic ZIP body exclusion. Local model servers are scripted; no external GPU request or tokenizer download is permitted in this verification environment. A new integrated Windows model run remains separate evidence.

## Local result (本機驗證結果)

| Selected scope | Passed |
| --- | ---: |
| Completion policy and body-free ZIP regressions | 10 |
| Existing repair module, including real SDK, API/JS, caps and cancellation | 15 |
| Authenticated Strata LLM/repair/GEPA plus exact GEPA perfect-seed case | 4 |
| Canonical M adapter with actual SDK over loopback | 1 |
| Existing diagnostic module | 13 |

All 43 selected cases passed without skips. Ruff on changed Python files, the source credential-pattern scan and diff checks passed. The actual uploaded failure was additionally projected through the new ZIP exporter: the baseline 3/6 and later 6/6 test counts, eight tool-call finish reasons, SDK cap failure and output limit survived export without raw bodies. This read-only check issued no model requests. No frontend or full M7 gate was rerun.

## Operator next step (操作方式)

Stop the GUI, pull the change and restart it in the same prepared Strata shell. Keep the tested endpoint/model, output budget, reasoning effort and call/time limits. Submit one new Python repair run. Existing failed results are preserved. No broad M7 rerun or repeated compatibility diagnostic is needed for this repair. If the next run fails, export the existing diagnostic ZIP before requesting another experiment.

## Follow-up: GUI task budgets (GUI 每題額度)

A later target run completed the single repair workflow and three GEPA rollouts with the summary phase. The next rollout needed read, baseline test, first write/test, corrective write/test and summary: seven requests when operating one tool per response. Its first repair passed two of three visible tests; the correction passed all three on request six. The six-request task cap correctly blocked request seven, while global calls and workflow time remained available. Final hidden evaluation did not run for that failed rollout.

The missing operational check was the GUI's independent six-request default. New GUI experiments now default to eight requests per task, including summary, with an explanatory label. Existing explicit choices, frozen runs, SDK caps, whole-run/per-call deadlines and acceptance-test fixture budgets retain their meaning. Default Smoke global capacity becomes 162 requests under the existing server formula (8 search + 12 final rollouts, times 8 calls, plus 2 proposals); this is a ceiling, not a promised workload or success guarantee.

Maintenance rule: when adding mandatory post-tool model work, audit form defaults and the actual submission payload as well as the runner. Count a baseline measurement and a corrective attempt, not only a scripted first-attempt success. Keep configuration defaults distinct from hard-limit enforcement and historical evidence. This follow-up changes GUI defaults and guidance only; no backend or M7 budget is silently expanded.

Follow-up verification: 26 focused frontend cases passed, including actual app submission, default eight, explicit six, and immutable uncertain-dispatch replay. A no-model configuration freeze confirmed task/global caps 8/162 with unchanged 1800/120-second workflow/call limits. Source scan and diff checks passed; no full GEPA or M7 rerun was needed for this GUI-only change.
