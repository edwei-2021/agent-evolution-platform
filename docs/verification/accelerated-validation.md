# Accelerated Workflow Verification (加速流程驗證)

Release **v0.7.1** preserves v0.7.0's provider, preload, rule/LLM Skill, nanobot, GEPA, release/rollback and monitoring behavior. Validation uses actual **nanobot-ai 0.3.5 / GEPA 0.1.4**, Python 3.12 and Node 24, with loopback model fixtures.

## Per-step acceptance tests (逐步驗收測試)

| Step/function | Tests | Result |
| --- | --- | --- |
| Log start/end/failure, duration, redaction, unavailable journal | `step_trace_test.StepTests` | Passed |
| Sync/async/tool spans and safe argument selection | `step_trace_test.StepTests` | Passed |
| Batch equivalence, fresh namespace, single isolated process, invalid size/syntax/output | `step_trace_test.BatchTests` | Passed |
| HTTP read-only step route, unknown Run and cross-origin denial | `step_trace_test.StepApiTests` | Passed |
| Staged profile, real SDK release requirement, stdout/report persistence and failure stop | `check_steps_test` | Passed |
| Frontend timing/status/schema, escaping, obsolete responses, read-only requests | `steps-client.test.js` | Passed |
| App navigation/refresh; original settings, warmup, logs, GEPA and repair controls | `app-forms.test.js` | Passed |
| Actual SDK/GEPA per-operation span coverage and terminal pairing | `gepa_test` actual optimizer case | Passed |
| All v0.7.0 functionality, deadlines/cancellation, independent final gates and tamper rejection | Complete existing JavaScript/Python suite | Passed |

## Release evidence (發布驗證)

The complete staged release check passed **91 JavaScript and 115 Python tests**, with no skipped SDK tests. A subsequently added focused real-HTTP step-boundary test also passed. Total distinct validated tests: **207 (91 JavaScript + 116 Python)**. The extra focused check avoids repeating the unchanged full suite. Check reports persist individual stage starts/ends, exit codes, stdout and duration. The full release Python stage took approximately 139.6 seconds on this machine; this is a test-run measurement, not an experiment speed guarantee.

The controlled evaluator measurement used the same 40 jobs and measured identical aggregate case outcomes. Python starts fell from 40 to 10; wall time fell from 1.1112 to 0.2681 seconds. No model result/session cache or independent final-evaluation removal is involved. The new reviewer/approval path recomputes trusted evidence and continues rejecting tampering.

## Reproduction and limits (重現方式與限制)

```bash
.venv-nanobot/bin/python scripts/check_steps.py --profile quick
.venv-nanobot/bin/python scripts/check_steps.py --profile release
```

The managed environment has no supported browser-control skill, so browser-engine visual QA was unavailable. No substitute browser or user Windows/GPU probe was run. Real HTTP/SDK tests and app-handler fixtures verify integration; local Ollama performance still depends on the user's machine/model. Step history is bounded by the existing 10,000-event journal and a 500-event read limit. Prior runs have legacy logs, with no invented retrospective spans. SDK/model failures remain bounded and are not automatically retried.
