# Measured Skill verification — 2026-10-11 (技能演化驗證)

Release: **v0.4.0**. Target: WSL2 Ubuntu 24.04, Python 3.11+, `/mnt/d/nanobot-gepa-mvp`, default port 8765.

## Environment checked first (先檢查環境)

The read-only installer doctor ran before implementation and after the new files were complete. Development environment: Ubuntu 24.04.3 container, Linux 6.18.44, Python 3.12.14, Linux Node 24.19.0 and an existing ready `.venv`. The doctor correctly reports NOT READY for the WSL target because the environment is not WSL2; image-provided command tools lack corresponding APT records. SQLite and Linux file locking work. No system packages, model SDKs or third-party dependencies were added.

The prior user-provided screenshot reports WSL2 Ubuntu 24.04.5 / Python 3.11.9 / Linux Node 22.23.3 with READY status. That host was not directly operated in this turn. New doctor checks cover the skill engine/store/role sources, GUI module, baseline Markdown and dataset files.

## Automated checks (自動檢查)

- **43 JavaScript tests:** existing demo/registry/polling coverage, plus seven skill contract/view/controller tests for active-version consistency, candidate metrics, stale/release gates, escaped traces, token/revision-bearing requests, immutable retries, definitive rejection recovery, historical selection, trials and old-version result labeling.
- **38 Python tests:** existing 25 installer/runtime tests plus 13 skill tests covering metadata/body/hash consistency, real policy execution, fixed disjoint fixture groups, actual exact-output success, training-only mutation probes/counts, real five-role PIDs, no auto-activation, immutable approval/rollback/restart, no-gain release rejection, trusted evidence recomputation, stale baseline/revision/idempotency handling, cancellation and HTTP skill routes/trials.
- Project-health's Python stage now runs `s*_test.py` (installer + Skill tests), excluding `runtime_test.py` to prevent recursive supervisor tests.
- Frontend module syntax and relative import targets, Python syntax, Bash syntax and `git diff --check` pass.

Real role tests record a baseline plus four candidates. Training executions total 220, validation 50, held-out 40, and separate reviewer verification 90. Candidate C4 measures validation 10/10 against baseline 2/10 and held-out 20/20 against baseline 4/20. These are actual output-equality measurements on a small handwritten fixture, not synthetic scores or a general agent benchmark.

## HTTP + frontend client integration (整合驗證)

A temporary actual loopback server uses the standard-library runtime. The default RuntimeClient is exercised with a receiver-sensitive relative-URL fetch shim, preserving the browser-global binding fixed in v0.3.1. It completes **55 refreshes** across this path:

1. Fetch capabilities/state and serve `skill-view.js` with HTTP 200.
2. Trial the baseline on full-width/case/whitespace text and retain the exact input.
3. Submit a four-candidate Skill workflow; observe five real role processes, zero exit codes, measured candidates and passing review.
4. Render the actual snapshot with both `skillView` and `runtimeView`; inspect candidate C4 and Skill task labeling.
5. Select history, approve/activate S1 at revision 2 and trial its actual output `service down`.
6. Start a second workflow from the optimized active baseline; finish with `keep-baseline`, then reject approval.
7. Reopen the first run, roll back to S0 at revision 3 and confirm the baseline output is restored.

Final state has two immutable versions. Temporary smoke data is removed; tests use project-local ignored temporary paths. No real provider, model, nanobot or GEPA call occurs.

## Verification limits (驗證範圍)

No Browser control skill is available for managed preview, so browser visual/mobile rendering and full DOM interaction QA were not performed. The HTTP/client/render-function checks do not substitute for a Chrome interaction test. Windows localhost forwarding, WSL Python 3.11, D / DrvFS behavior and live APT downloads were not directly tested.

The dataset is small and visible to repository developers. Search-function input separation keeps validation/held-out records out of candidate generation, but does not hide source data from a human. Repeated evaluation reveals the fixed holdout. No claim is made about LLM reasoning, free-form prompt evolution, GEPA convergence, Python repair, runtime installations or remote WSL access.

Approval changes a local server-owned version pointer. It does not push runtime logs to GitHub, publish an external-agent Skill or change private Site sharing. Source software/docs/tests are independently version-controlled in `nanobot-gepa-mvp`.
