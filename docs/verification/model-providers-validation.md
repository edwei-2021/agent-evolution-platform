# Selectable model-provider validation

The change adds independent Ollama/Strata profiles and provider-specific routing while preserving bounded shared model ownership, frozen run settings and independent review. The real supplied Strata diagnostic passed chat, tool calls, tool-result continuation and SSE; its private endpoint/model and support archive are not published here. This is API compatibility evidence, not integrated real-model or full M7 acceptance.

Final local checks (counts are unique selected cases, not repeated attempts):

| Scope | Passed |
| --- | ---: |
| Provider profiles/routing/authentication/native load/redirect/endpoint identity | 7 |
| Existing Ollama bridge/API | 8 |
| Existing warmup lifecycle/deadline/cancellation | 7 |
| Existing bounded stream transport | 6 |
| Strata authenticated real SDK role workflows: LLM, nanobot repair, GEPA | 3 |
| Ollama real role workflow regressions: LLM, nanobot repair, GEPA | 3 |
| Categorized diagnostics and support export | 17 |
| Frontend provider/forms/warmup/runtime | 29 |

All selected cases passed without skips: 51 Python and 29 JavaScript cases. Ruff on changed Python files, the source credential-pattern scan and `git diff --check` passed. A separate M CLI configuration-only check verified that the frozen provider and model-policy identity agree, stopping before adapter/model/Docker execution.

Real SDK checks used nanobot-ai 0.3.5 and GEPA 0.1.4, authenticated loopback JSON/SSE fixtures and actual role processes. Non-loopback DNS/connections were denied before dispatch during verification; no tokenizer download was allowed. The Strata GEPA case recorded 18 rollouts, 54 trusted verification batches (three per rollout), 46 model requests, nine visible-test tool calls, then four additional approval/tamper replay passes. Independent reviewer, release eligibility, rollback and tamper rejection passed.

The focused fixture module reuses the existing calibrated workflow and call/cleanup limits. No M7 manifest, workflow budget, SDK cap, evaluator grammar or model-call budget was expanded. The user-facing next step is one integrated real Strata repair run; previously successful standalone API checks need not be repeated. Strata native loading is source-contract/loopback tested only. Real Windows GUI execution, model quality, browser visual QA, Docker and full phase M remain outside this local result.
