# LLM Skill Verification (LLM 技能驗證)

Version: 0.5.0. Development host: Ubuntu 24.04.3, Python 3.12.14, Node 24.19.0; project `.venv` present. This is a Linux container, not the user's Windows/WSL host. The target installer check reports missing APT packages here, while development executables are available. No target installation or Windows configuration was performed. The new code uses only Python standard-library modules.

All model tests use a loopback mock Ollama. No Windows connection diagnostic, metadata probe, model download or real Windows inference was attempted. The user's supplied metadata success remains unchanged.

| Verification | Result |
| --- | --- |
| Smoke real subprocess/HTTP workflow | 15 recorded calls; baseline and candidate output scoring, five actual PIDs, no auto-activation |
| Full real subprocess/HTTP workflow | 101 recorded calls; 20/10/20 splits and held-out scoring |
| Reflection isolation | Only training failures sent; model task payloads contain no expected outputs |
| No improvement | Baseline retained; 13 Smoke calls; approval rejected |
| Provider/candidate failure | No automatic retries; failed evidence retained; downstream roles skipped |
| Evidence tampering | Modified raw model output blocks version approval |
| Cancellation and provider slot | Active subprocess stopped, future calls prevented, concurrent workflow/manual provider requests rejected |
| Whole-run deadline | Waiting subprocess terminated; later calls prevented; native-tool stage deadline does not truncate LLM runs |
| Version review/restart/rollback | Immutable LLM versions, persistent active pointer, separate rule state and optimistic revisions |
| Browser transport + real Python API | Actual RuntimeClient polling, submission, completion, history, approval and rollback; mock model only |
| Web rendering/control tests | Escaped body/output, stale-evidence gates, fixed revision/idempotency body, no preflight network probes |

Coverage added in this phase: 12 Python tests and 5 JavaScript tests. **Full regression passed: 52 JavaScript + 58 Python tests, 110 total.** The Python suite completed in 54.069 seconds and includes actual role subprocesses, rule-workflow regression and the browser transport/API integration. Changed Python/JavaScript syntax, Bash syntax and `git diff --check` also passed. A final prompt-size boundary correction was rechecked with the complete 12-test LLM subset. Browser visual/full DOM QA and real target-model behavior are not claimed. Mock scores establish execution/evidence/control correctness only.
