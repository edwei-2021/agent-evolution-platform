# Accelerated Delivery Plan (加速開發規劃)

## Release sequence (版本順序)

Each release has one concrete outcome and a small acceptance gate. Preserve **all v0.7.0 features** in the regression suite: saved model settings, explicit preload, rule/LLM Skill experiments, bounded nanobot repair, actual GEPA, independent final evaluation, human approval/rollback, progress and module logs.

| Release | Scope | Acceptance gate | State |
| --- | --- | --- | --- |
| **v0.7.1** | Structured step logs, per-step timing/view, bounded batch evaluator, staged test reports | Focused step tests, actual SDK integration, all existing regressions | Implemented in this delivery |
| Next | User-authored grouped repair datasets and validated import | Schema/size/group separation tests, trusted evaluator references, then Smoke | Planned |
| Later | Multi-file repair inside a container boundary | Filesystem/network/tool isolation first, then new task contracts | Planned |

Remote workers and external-agent Skill publication remain separate. This plan avoids coupling new dataset design and container work to the current operational improvements.

## Small delivery steps (小步驟交付)

| Step | Change | Required evidence |
| --- | --- | --- |
| 1 | Freeze scope and measure a real bottleneck | Same inputs/results before and after; no model-quality claim |
| 2 | Structured step events | Start/end/failure, stable step ID, monotonic duration, redaction and storage-failure tests |
| 3 | Batch trusted tests | One isolated process per verification, fresh namespaces per job, identical scores, malformed/oversized batch rejection |
| 4 | Read-only step API and GUI | Same-origin/run boundary, correct timing/status, escaped text, obsolete-response rejection |
| 5 | Instrument original workflows | Real SDK calls/tools, GEPA stages/final/review, legacy model/rule roles, supervisor processes and mutations |
| 6 | Release | Full JavaScript/Python regression in pinned SDK environment, then source/package checks and private deployment |

Run focused tests after each change. A failed step stops its check profile and keeps stdout, exit code, time and error. Run the full release profile once when the changed inputs stabilize; repeat only affected checks after a later isolated change. Publication still requires all material checks to pass. No additional approval round is added to the user's already-authorized GitHub/private-Site updates.

## Faster verification (加速驗證)

v0.7.0 started several Python evaluators for each source/split and replayed test tool. v0.7.1 collects the source/split jobs for one evidence verification, deduplicates identical jobs **inside that verification**, and uses one bounded isolated interpreter. It recomputes the evidence in every reviewer/approval verification. This does not cache a model response, reuse an agent session, remove a final task, or trust a stored passing score.

Constraints remain: at most 32 jobs, 1 MB request, 5-second subprocess deadline, 2-second CPU allowance, 256 MB address-space cap and the existing pure-function AST subset. Each job creates a new namespace. This remains a constrained evaluator, not an arbitrary-Python OS sandbox.

Local controlled measurement, 40 identical source/split jobs:

| Measurement | Before | After |
| --- | ---: | ---: |
| Python processes | 40 | 10 |
| Elapsed time | 1.1112 s | 0.2681 s |
| Sum of passed cases | 160 | 160 |

The evaluator portion was approximately **4.14× faster** on this machine. This does not predict Ollama latency or end-to-end experiment speed. Model requests remain serial and bounded; saved preload is explicit. Full experiments still have more tasks than Smoke. Use per-step time records to identify the next measured bottleneck.

## Step observability (逐步可觀測性)

Every instrumented operation writes `STEP_STARTED` and one terminal event (`STEP_COMPLETED`, `STEP_FAILED`, `STEP_CANCELLED` or `STEP_INTERRUPTED`) to the existing bounded journal. Records include a unique step ID, step/module, parent Run ID, optional role/task/artifact/tool, duration and redacted error. Argument bodies and prompt/source contents are not copied into general logs. Detailed model/test artifacts remain unchanged.

Open `http://localhost:8765/#steps` for **逐步執行紀錄**. Select the Run, inspect durations, and use **模組 Log** for raw records and older pages. The API reads at most 500 matching events; journal retention can remove older events. Missing starts are shown as partial history. A killed subprocess may have no inner completion event; a terminal Run shows that span as **unreported** (結束前未回報), not a fabricated success.

Supervisor process spans cover every original workflow, including project checks. LLM/model calls and task evaluation, nanobot SDK/tool/model/evidence operations, GEPA rollouts/proposals/search/final/review, and API mutations provide finer spans. Explicit preload retains its existing dedicated progress/journal records; its submission/cancellation operations also receive API spans. Browser-local synthetic demos have no backend execution spans.

## Staged test command (分層測試指令)

Run from the WSL checkout:

```bash
.venv-nanobot/bin/python scripts/check_steps.py --profile quick
.venv-nanobot/bin/python scripts/check_steps.py --profile model
.venv-nanobot/bin/python scripts/check_steps.py --profile release
```

Use `quick` for step/evaluator micro-tests and all frontend regressions. Use `model` when SDK/GEPA behavior changes. Use `release` before publication; it runs all frontend and all Python tests and requires real pinned nanobot/GEPA packages. Release checks do not accept absent SDKs as a skipped-test pass. These profiles execute loopback fixtures; they send no requests to the user's Windows Ollama/GPU.

Reports and per-stage stdout are under `.local/test-reports/CHECK-.../`. Each report records running/terminal status and timing, including failures. The same `CHECK-...` ID filters test-step events on the module Log page. These local reports are excluded from Git; the release verification document records the delivered results.

## Upgrade (更新方式)

Stop the GUI, pull v0.7.1, and restart. Existing v0.7.0 SDK packages remain pinned; this release adds no dependency. Refresh the browser with Ctrl+Shift+R. Existing versions/settings are retained. Prior experiment logs remain readable; step spans are produced by new executions. Code provenance changes require a fresh experiment before approving a candidate from the new code.

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/start-gui.sh
```
