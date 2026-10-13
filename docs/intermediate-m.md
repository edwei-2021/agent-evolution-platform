# Intermediate Phase M Implementation and Operator Guide

This delivery adds M service components and machine checks to the v0.7.1 runtime. Existing GUI/model settings and legacy runs remain supported. It does not certify the entire hardened platform as complete. Container acceptance must run on Docker-capable Ubuntu/WSL; real Windows model quality and full production migration remain unverified.

## 1. Delivered programs by step (各步驟程式)

| Step | Programs/scripts | Implemented checks | Remaining phase closure |
| --- | --- | --- | --- |
| M1 | migrate_wsl.py; Store.backup; source inventory | State backup/restore, checked move, running-service refusal; legacy frontend regression | Execute migration/restore on the actual WSL checkout |
| M2 | contracts.py; adapters.py; generate_m_contracts.py; m_nanobot_worker.py | Strict schemas, generated-client checksum/typecheck, deterministic mock statuses and actual nanobot SDK over loopback | Wider real task/runtime capability verification |
| M3 | store.py; worker.py; api.py | Idempotency, lifecycle, lease/fence, interrupted state, checkpoint immutability and SSE replay | M queue is additive; historical legacy DB is not silently rewritten into the new ledger |
| M4 | evaluator.py; evaluator.Dockerfile; build-m-images.sh | Digest, no-network/read-only/non-root/capability/resource policy, malicious AST rejection and cleanup | Real Docker gate required; bounded pure-function tasks only, not arbitrary repository code |
| M5 | dataset.py; run_m_repair.py; run_m_comparison.py | 20/10/20 linter, feedback whitelist, matching comparison, per-task regressions and uncertainty | Real GPU comparison and approved candidate provenance/selection verification |
| M6 | releases.py; budget.py; m_admin.py | Ed25519/RBAC, CAS integrity, validation/final gates, parent/revision activation, rollback, persisted task checkpoints | Optimizer-internal GEPA search resume and Git manifest reconciliation are not claimed complete |
| M7 | uv.lock; FastAPI facade; Compose; CI; check_m.py | API auth/origin/correlation, static TypeScript, staged checks, support bundles, SDK regression | CI/image health and WSL service verification; full GUI/RBAC migration and browser QA |

The acceptance script proves the listed machine-check scope. A green component gate is not proof that the remaining phase-closure items are finished. Current API queue accepts explicitly labeled mock work; actual nanobot work uses the explicit scripts below. No process automatically sends model requests at install/startup.

### M1 pytest capture issue on WSL DrvFS

If M1 reports `FileNotFoundError` from `_pytest.capture` while truncating its capture tempfile and says no tests ran, this is a pytest output-capture failure, not a migration assertion failure. M acceptance now invokes pytest with `-s` so its internal file-descriptor capture is disabled; the outer gate still captures and saves stdout/stderr in the M1 support bundle. If the rename test then reports `PermissionError` under `/mnt/d`, the test fixture was on DrvFS, whose directory rename can be denied even on the same drive. The rename-mode fixture now runs on Linux's native temporary filesystem; the verified-copy test continues to exercise the supported `/mnt/d` path while preserving the source. The M1 frontend command resolves the repository's pinned Node runtime, so acceptance does not depend on the interactive shell's `PATH`. After pulling these fixes, run `.venv-m/bin/python scripts/check_m.py --profile acceptance`; this resumes at M1 without reinstalling the environments.

## 2. Upgrade and Ubuntu path migration (Ubuntu 目錄遷移)

Stop the legacy GUI, M API and worker first. Run in the existing checkout:

```bash
cd /mnt/d/nanobot-gepa-mvp
git remote set-url origin https://github.com/edwei-2021/agent-evolution-platform.git
git pull --ff-only
python3.11 scripts/migrate_wsl.py --destination /mnt/d/agent-evolution-platform
python3.11 scripts/migrate_wsl.py --destination /mnt/d/agent-evolution-platform --apply
cd /mnt/d/agent-evolution-platform
bash scripts/install-wsl.sh --python python3.11
bash scripts/install-nanobot.sh
bash scripts/install-m.sh
npm ci --ignore-scripts
```

Install uv first if missing, following [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/). The M installer reports a blocked dependency instead of silently installing an unknown system tool.

The migration dry-run changes nothing. Apply checks stopped-service locks, same-filesystem/absent destination, copies a backup under .migration-backups, validates SQLite databases and compares .local file hashes. It moves the checkout, updates origin and retains old virtual environments under .before-migration names. Rebuild environments to repair absolute shebangs; keep the backup until acceptance passes. Existing model endpoint/port/model and run/version records are preserved. The underlying Windows Ollama is not reconfigured or re-tested.

If already using /mnt/d/agent-evolution-platform, omit the move commands. A different desired path may be passed explicitly. File paths in installers/start scripts derive from the checkout root.

### Windows drive rename denied

If the root directory rename returns Permission denied, retain the original checkout and backup. Use the verified-copy path; it keeps source service locks during the copy, omits non-relocatable virtual environments, verifies state hashes and SQLite integrity, updates the new origin, then exposes the destination. It never deletes the source.

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
cd /mnt/d
python3.11 nanobot-gepa-mvp/scripts/migrate_wsl.py \
  --destination /mnt/d/agent-evolution-platform --copy --apply
cd /mnt/d/agent-evolution-platform
bash scripts/install-wsl.sh --python python3.11
bash scripts/install-nanobot.sh
bash scripts/install-m.sh
npm ci --ignore-scripts
```

Use only the new checkout after success; keep the old one until acceptance passes. If copy fails, migration-copy-error.json identifies retained staging/backup paths. Do not merge into an existing destination or remove source data to retry. Windows permissions and open handles can still block reads or writes; copied files are not a permission bypass.

## 3. Checks and expected results (驗收及預期結果)

```bash
cd /mnt/d/agent-evolution-platform
.venv-m/bin/python scripts/check_m.py --profile components
bash scripts/build-m-images.sh
.venv-m/bin/python scripts/check_m.py --profile acceptance
```

- Components: fast development checks; Docker isolation may be skipped and must not be presented as phase acceptance.
- Acceptance: M1 through M7 in dependency order; M4 requires a running Docker daemon and locally built evaluator image. M7 requires actual installed nanobot/GEPA, full legacy regression, lint and generated TypeScript checks.
- Before every acceptance command, the gate prints `M_CHECK_EXPECTED` with the command, normal-duration estimate, continue-prompt threshold and hard limit. Child output streams to the terminal and support bundle with redaction. Every five seconds after normal duration it prints `M_CHECK_OVERRUN`; at ten times normal duration (capped at 30 minutes) it asks whether to continue. `y` continues with periodic overrun reports; any other response stops the process group. Successful command timings are retained and used for later estimates.
- Success: each step stores a passed StepCheck; final report status is passed within the declared machine-check scope.
- Failure: failing step is failed or blocked, later steps are blocked and their commands do not run; command exit status is nonzero. Dependency preflight uses exit 78 and is recorded as blocked.
- Every bundle is under .local/m/support/MCHECK-.../M1.json through M7.json. report.json links the checks. Bundles include source/input hashes, command, exit code, redacted combined stdout/stderr and remediation. Checks also persist in control.sqlite3 independently of debug-log rotation.

Do not rerun expensive model experiments to diagnose a dependency failure. Correct the reported cause, then rerun acceptance. Installing dependencies/building images sends no Ollama requests.

## 4. Local API and mock worker

```bash
bash scripts/start-m.sh --port 8767
```

API binds only 127.0.0.1. The owner-only bearer token is stored in .local/m/operator.token and is never printed, committed or placed in the frontend. Health is GET /api/m/health. Protected endpoints include jobs, cancellation/resume, SSE replay, StepChecks and release approval/activation. Operator role is the default; --approver explicitly enables local-owner release authority. Caller JSON cannot choose its own role.

Run a separate mock worker:

```bash
.venv-m/bin/python -m platform_m.worker
```

For a compatible GUI facade, start the existing GUI on 8765 separately and run:

```bash
bash scripts/start-m.sh --port 8767 --legacy-port 8765
```

The facade forwards only fixed-loopback /api/v1 routes. Legacy GUI uses the existing local session token; M control routes use the separate bearer token. Hosted static GUI does not run this API or worker. Full new GUI integration is not claimed.

Docker option: docker compose -f infra/m/compose.yaml up -d after image build. The control service uses Linux host networking but binds loopback; worker has no network. Do not mount the Docker socket into the API. The evaluator is invoked separately by the host runner with no host filesystem mounts. Record the final image ID; builds record actual pulled dependencies rather than assuming a mutable base tag is reproducible forever.

## 5. Explicit real nanobot execution

Warm the saved model manually in the legacy GUI, then stop that GUI before real M scripts. They take its runtime lock to prevent overlapping provider calls. A single task:

```bash
.venv-m/bin/python scripts/run_m_repair.py --experiment local-smoke-001 --task PY-clamp-1
```

This uses pinned nanobot, fresh workspace/session, the named Skill, container-backed visible/hidden checks, a RunResult and independent Evaluation. SDK output alone never becomes a score. .local/m/runs/MRUN-... contains traces; CAS and the immutable database contain references. Docker is mandatory; missing isolation has no host fallback.

To compare a prepared candidate Skill body (plain text, <=8 KB), first check the budget. Default comparison runs 10 validation tasks once and 20 independent tasks three times for each Skill: 140 task executions, up to 840 model calls with six calls per task. Output-token and latency ceilings remain those in the saved provider/configuration.

```bash
.venv-m/bin/python scripts/run_m_comparison.py \
  --experiment comparison-001 \
  --candidate-body skills/candidate-body.md \
  --model-call-budget 840 --repetitions 3 --calls 6
```

The candidate file is user-supplied; it is not created by this installer. Do not use the independent set repeatedly to tune it. This script compares prepared Skills; it does not claim to resume GEPA's internal optimizer state. Legacy GEPA search remains available through the existing GUI. Selection provenance must be verified before a production release.

Completed task results can be reused on identical resume inputs; ambiguous/failed attempts stop for inspection and are not silently reissued. Experiment snapshots reject changed model/data/code/image/budget/Skill. Tasks alternate baseline/candidate order. progress.json and persisted task events record completed/total work. Invalid evaluation stops dependent work. This tool may retain S0; improvement is not guaranteed.

## 6. Release administration

```bash
.venv-m/bin/python scripts/m_admin.py init-key
.venv-m/bin/python scripts/m_admin.py dataset
.venv-m/bin/python scripts/m_admin.py active
```

Register an operator-prepared complete Release manifest referring to CAS assets and immutable evaluation IDs. Registration reruns protected hidden tests from the frozen candidate source/fixture/image; synthetic mock queue records cannot become a real release:

```bash
.venv-m/bin/python scripts/m_admin.py register --manifest .local/m/release.json
.venv-m/bin/python scripts/m_admin.py approve --hash MANIFEST_SHA256 --rationale "Reviewed matching evidence"
.venv-m/bin/python scripts/m_admin.py activate --hash MANIFEST_SHA256 --expected-revision 0
```

Replace MANIFEST_SHA256 with the returned hash. The register gate recomputes comparison from stored records, verifies artifacts, requires matching complete validation with improvement, repeated independent evidence and zero regressions. A checksum is not a signature: Ed25519 signs immutable manifest bytes with the server-side owner-only key; the trusted public key is checked during activation. Key rotation requires a deliberate migration; replacing a key invalidates previous verification.

The signing key is stored with owner-only permissions in the Linux user's state directory by default, outside a `/mnt/<drive>` DrvFS checkout. `init-key` prints its path. `AEP_SIGNING_KEY_PATH` can select a different protected path for an API service and its administration commands; set it in both processes. Existing `.local/m/signing.key` files remain in use to preserve prior signatures. If a legacy key on DrvFS fails the permission check, copy the same key bytes to a Linux-native path with `mkdir -p "$HOME/.local/state/agent-evolution-platform" && install -m 600 .local/m/signing.key "$HOME/.local/state/agent-evolution-platform/signing.key"`, then set `AEP_SIGNING_KEY_PATH` to that path for both processes. Do not generate a replacement key for a database with existing approvals; its signatures would no longer verify.

Rollback targets the current release's approved parent and requires the current pointer revision. Activation changes future snapshots, not in-flight manifests or historical evidence. This new release pointer does not silently change the legacy rule/LLM/GEPA active pointers. Final production cutover and Git reconciliation remain separately gated.

Back up the stopped service's entire .local/m (DB and CAS), the signing key at the path printed by `init-key`, and existing .local data. backup-db can produce a transactionally consistent DB copy but is not a complete artifact/key backup by itself.

## 7. Debug support matrix

| Code | Inspect | Action |
| --- | --- | --- |
| DBG-M-001 | migration report, source/destination, locks, SQLite integrity | Stop services; preserve backup; resolve path/permission/hash failure |
| DBG-M-002 | schema checksum, strict validation, SDK version, loaded Skill hash | Sync locked packages; regenerate schema; inspect requested/observed Skill |
| DBG-M-003 | job state, idempotency key, owner/fence/lease, event sequence | Reconcile expired worker; preserve checkpoint; explicitly review resume |
| DBG-M-004 | Docker info, image ID, resource flags, evaluator result, cleanup | Enable WSL integration; build image; quarantine unconfirmed cleanup |
| DBG-M-005 | task family/split/hash, paired results, invalid verdict, regression list | Correct data/snapshot; retain baseline if improvement gate fails |
| DBG-M-006 | manifest/result IDs, signature, key mode, role, pointer revision | Restore verified artifacts/key; refresh revision; require complete evidence |
| DBG-M-007 | uv/npm locks, TypeScript/lint, API request ID, legacy release log | Fix failed dependency/check; rerun affected checks then acceptance |

No Windows/GPU speed or model-quality result is inferred from loopback tests. Docker behavior, production cutover, optimizer search resume and actual user WSL execution remain explicit closure work.

### First mock LLM workflow timeout during WSL installation

If installation reports LLM workflow did not finish, stop at that failed gate. Update the checkout and run the single-case probe before repeating all tests:

```bash
cd /mnt/d/agent-evolution-platform
git pull --ff-only
.venv/bin/python scripts/check_llm_first_failure.py
```

The current probe follows the frozen workflow budget (60 seconds in this fixture) plus 10 seconds for terminal cleanup, uses only a loopback mock model, and bounds the test harness to 120 seconds. The former unrelated 20-second workstation-speed assumption is superseded. Its report and test log are stored under .local/test-reports/LLM-CHECK-...; on failure it also captures role states/log tails, mock request count and periodic Python thread stacks. These distinguish process startup, progress I/O, lock waits and model transport. A timeout is not silently converted to a pass.

Progress reads now release the supervisor mutex before filesystem access. A disconnected HTTP client closes the response without attempting a second error response. These defects are regression-tested; the user's WSL timeout still requires the local probe result. The installer prints Python case names and stops on the first failure. Optional GEPA/nanobot skips in the base GUI environment are not equivalent to an SDK acceptance pass.

### Journal commit latency identified by a thread snapshot

A user WSL probe completed nine mock calls in approximately 2–6 ms each, while the supervisor stack was in DebugLog.append transaction exit during role-log capture. This identifies synchronous journal I/O as an observed latency source, not evidence of a model hang or proof of a deadlock.

The debug journal now uses bounded append_many transactions (1..128 records), one retention operation per batch, WAL synchronous=NORMAL and one idle supervisor-lifetime connection. This avoids per-record FULL fsync and repeatedly checkpointing on the last connection close. Role log capture and log-tail reads occur outside the supervisor mutex. Redaction, ordered IDs, bounds, restart visibility and all captured line counts remain tested. Explicit close releases the keeper during shutdown.

The policy applies only to supplementary debug.sqlite3. Run/evaluation/release stores and the authoritative M ledger are not changed. With NORMAL, a power loss may discard recent supplementary log transactions; this is not the durability policy for release evidence.

```bash
git pull --ff-only
.venv/bin/python scripts/measure_debug_journal.py
.venv/bin/python scripts/check_llm_first_failure.py
```

The measurement compares current single-record writes with one batch on the actual project filesystem, including final close/checkpoint. Both paths must retain the same record count. It sends no model requests and does not measure the pre-fix FULL policy or predict GPU speed. A user D-drive result was 8.095 seconds for 40 single transactions and 0.184 seconds for one batch; this is evidence of transaction cost, not an inference benchmark.

### Completion-policy alignment and one-pass setup

Functional completion now uses an Event signalled after terminal persistence and provider-slot cleanup, rather than repeatedly querying SQLite every 25 ms. The test then reads the persisted terminal result once. It follows the existing maxSeconds budget plus bounded cleanup grace; model-call and workflow execution limits remain in the supervisor, and cancellation/failure are never reclassified as success. Assertions still require the five roles, 15 real mock requests, trusted scores and version gates.

Source and persistent state remain in the D-drive checkout. A slow host-filesystem benchmark is reported separately from functional completion. No implicit relocation to Linux home/tmp or Windows permission changes occurs.

With the GUI/API/worker stopped, run the automated setup driver:

```bash
cd /mnt/d/agent-evolution-platform
git pull --ff-only
python3.11 scripts/complete_m_setup.py --python python3.11
```

It runs the single-case gate when .venv already exists, the base installer, pinned nanobot/GEPA installer, uv bootstrap when missing, locked M installation, npm ci and strict M acceptance. Each command has a finite timeout; it prints live output and five-second wait updates. Failure blocks subsequent commands and retains redacted logs/report.json under .local/setup-reports/SETUP-.... --setup-only omits phase acceptance and labels that restricted scope explicitly. It never runs the user's model or cold-load diagnostics. Once the automated driver is launched, inspect its returned report instead of manually repeating successful stages or reinstalling unrelated components.

This changes the completion criterion from an arbitrary 20-second machine-speed expectation to the declared execution contract. It does not prove that a slow D-drive deployment meets a separate latency SLO, or complete the outstanding production/GUI/optimizer-resume migration work.

### Timeout verification on the WSL D-drive

The user setup report confirms that the single LLM workflow gate passed. Base validation then exposed a separate five-second assertion that measured startup, model timeout, journal commits and cleanup together (8.65 seconds on that host). Integration timeout cases now require the frozen one-second call budget, failed terminal evidence, zero completed calls, exactly one request and provider-slot release. Controlled-clock transport tests separately prove that continuous chunks and connection time consume the original absolute deadline without resetting it. The workflow completion budget remains bounded; inference limits are unchanged.

After updating, rerun the setup driver above. It creates a new report and revalidates the single gate and base environment before proceeding to SDK/M installation. Reports from previous attempts remain available. This driver currently repeats earlier validation steps when restarted; it does not implement resumable setup.

### Full-profile validation budget and trace overhead

The next WSL report confirms that the trickle timeout case passed. The full profile then correctly failed its frozen 60-second workflow deadline at 43 of 101 calls. Recorded model responses took approximately 13–22 ms each; this is an end-to-end storage/orchestration budget failure, not a model timeout. Nested runner spans now reuse their existing debug journal, avoiding repeated schema/index initialization while retaining immediate start and terminal events and log-root routing.

The 101-call functional integration case explicitly freezes a 300-second workflow budget before dispatch. Smoke cases remain at 60 seconds; single-call limits, call counts, data isolation and forced workflow-deadline tests remain unchanged. This deliberate full-test budget change does not alter production defaults or establish a storage latency SLO. Failure at that budget remains a failure. Restarting setup revalidates earlier stages and retains previous reports.

### Adaptive validation budgets (自適應驗證預算)

Setup now measures five bounded journal-transaction plus atomic-JSON-write samples on the actual checkout filesystem before dispatch. It derives smoke/full workflow budgets from 15/101 calls, the mock provider's ten-second per-call limit, measured storage allowance, and role/cleanup allowance. The former fixed 60/300-second functional-test budgets are superseded by this calculation. The workflow cap remains 7,200 seconds; excessive/invalid measurements block execution with DBG-ADAPT-001/002 instead of silently clamping or extending a running deadline. Calibration sends zero model requests and deletes its temporary files.

The setup report retains calibration samples, calculated budgets and filesystem path. One frozen calibration is passed to child processes so the single-case harness, Python workflow cases and JavaScript browser workflow use consistent limits. The outer setup validation timeout follows these calculated workload budgets. Direct unit tests retain calibration at .local/test-reports/validation-calibration.json. Single-call limits, forced deadline tests, no-retry assertions and production defaults remain intact. Storage allowances are conservative estimates rather than a latency guarantee.

Run the same complete_m_setup.py command after pulling changes; no manual timeout editing or separate timing experiments are required. Each failed step still blocks dependent installation and keeps its report/log. The controller cannot access the user's WSL directly; one local invocation is required to execute the automated process on that machine.

### Native crash diagnostics (原生崩潰診斷)

A subsequent WSL single-case gate exited with SIGSEGV (-11) at 25.65 seconds, well before its adaptive deadline. The previous shell code 245 was a wrapped negative process return code, not a timeout. The timing is close to the former 25-second native faulthandler watchdog; this correlation does not establish the root cause. The periodic native watchdog is removed. Python-level thread/state snapshots now run every five seconds without SQLite queries, and a fatal-signal handler records native failure evidence. Signal failures remain blocking and are never automatically retried or converted to passes.

The single-case report records the original signal and uses DBG-LLM-CRASH plus a stable wrapper exit code 2. It retains fatal.log, environment.json (Python/SQLite/platform versions), Python threads.log, periodic failure-state.json and role tails. Failed checks automatically create support.zip containing the retained JSON/log files. Early startup crashes are also captured through Python -X faulthandler stderr. Adaptive execution budgets are unchanged. Local SIGSEGV fault injection verifies signal classification and fatal-trace retention; it does not prove that the user's original native crash is resolved.


### Quick installation checks and long-running test prompts

The latest WSL run completed the single-case LLM gate in 38 seconds, then ran 91 Python tests for 602 seconds. It failed when the nested native-workflow test hit a 30-second poll timeout; 19 optional SDK tests were skipped. The base installer had been running the full Python suite even though M7 already owns the complete SDK-backed release regression.

Base installation now runs the saved `quick` profile: focused installer, setup, completion, journal, transport, trace and polling tests plus frontend tests. It omits the broad LLМ workflow suite and nested full test execution. The environment report labels only quick checks as passed and defers full regression to M7. The nested runtime workflow test now waits for terminal persistence with a bound derived from the supervisor's five per-role limits.

Before each supervised command, the runner prints `STEP_EXPECTED` with its expected normal duration, the continue prompt time, and its hard limit. Setup stages print the same information as `SETUP_EXPECTED`. Normal duration comes from recent successful runs of the same profile and step (1.5× the median); on a first quick run, Python-step estimates use test-case count and measured filesystem write cost, while frontend checks use 45 seconds. Setup stages learn from prior successful runs of that stage and use their configured baseline on the first run. Every five seconds past normal, the runner reports elapsed time and seconds over normal. The continue prompt is scheduled at 10× normal, capped at 30 minutes, and never before the normal duration. Entering `y` continues the test and its periodic reports; any other response or end-of-input stops the process and records that choice. At the finite hard limit, `TEST_HARD_LIMIT` or `SETUP_HARD_LIMIT` reports elapsed and overdue time before stopping the process. M acceptance has a 600-second first-run baseline, so it prompts after 30 minutes and retains its 7200-second hard limit. The single-LLM workflow also has its own frozen deadline; if that inner workflow reports failure or terminates first, the outer runner preserves that result. Waiting never converts a failure to a pass.


### Per-step release testing and timeout diagnosis

The WSL acceptance output captured M7 `all-python` at 1,610 seconds elapsed against a fixed 900-second normal budget. Its continue prompt was set for 1,800 seconds (10× normal, capped at 30 minutes), so Ctrl-C arrived before the prompt threshold. The release regression is now split into `all-frontend` and one `python-<filename>` step per `tests/*_test.py`; each module streams flushed test-case start/result events, records case and module durations in the report, uses a module-specific adaptive budget, and emits a 30-second progress heartbeat. A visible filesystem-calibration step measures journal and atomic-file I/O before first-run module estimates; it sends no model requests. Later estimates use that module's successful timing history. The outer M gate suppresses duplicate overrun heartbeats while the child supervisor remains active. M1–M7 pytest commands now print each case name and the completed-case duration summary. M2 and M7 tests that cover multiple files are separate timed commands. Each command retains its own expected duration, timeout decision, measured result, and support bundle.

Ctrl-C/SIGTERM is recorded as an interruption distinct from declining the continue prompt; the current module report is finalized with completed case timings and the interruption reason.

### M7 GEPA first-failure diagnostic

The WSL release report `CHECK-fc12165f4daf4073a672275eb22e6cfc` finished the first seven commands, then `python-gepa_test` failed after 640.5 seconds. Its earliest error was the JavaScript client integration case, which exhausted its own 90-second subprocess limit. The old module runner continued nine further cases, adding several minutes. The release module runner now stops on the first error. A failing GEPA case retains a thread snapshot, a small status summary, and a copy of its temporary runtime directory before cleanup.

Run only the earliest failing case, with filesystem calibration, a 15-second progress heartbeat, normal-time overrun reports and one saved diagnostic report:

```bash
.venv-nanobot/bin/python scripts/check_gepa_first_failure.py
```

The command prints `GEPA_DIAGNOSTIC_REPORT` and, on failure, `GEPA_DIAGNOSTIC_ARCHIVE`. The archive is under `.local/test-reports/GEPA-DIAG-<id>/failure-evidence/gepa_test/`; it contains `diagnostic.json`, `threads.log`, and `run/.local/runs/RUN-<id>/` with the GEPA progress, model calls, role logs and available search/final artifacts. A passing targeted case has no failure archive. The WSL run is needed to locate its platform-specific wait; passing local loopback runs do not establish that the WSL run will finish within the same time.

### M7 WSL GEPA diagnostic: JS integration budget (2026-10-13)

The WSL single-case evidence in `GEPA-DIAG-c5075f7a701c490bbdef730e0acbd912` shows the JS client waiting for the Python GEPA run. At 90 seconds, the coordinator, worker, and reflector had completed; evaluator had just started and reviewer was queued. Six serial search rollouts were complete, and independent final evaluation still required up to twelve more. The Node subprocess then hit its fixed 90-second test timeout, while the frozen GEPA workflow had a 120-second limit. The captured `threads.log` shows the supervisor waiting for its child process; the last model call had completed. The 90-second failure was a test budget mismatch, not evidence of a stuck model request.

The GEPA smoke integration tests now calculate a pre-dispatch budget from the filesystem calibration and the maximum serial workload (eight search and twelve final evaluations). The JS child receives the same frozen workflow limit; its own timeout and the Python completion wait include bounded cleanup time. The JS case prints `GEPA_TEST_PROGRESS` with the running role, phase, completed rollouts, and active rollout every ten seconds. The single-case diagnostic prints the calibrated normal time before dispatch. For the uploaded WSL calibration of 2.032 seconds per I/O allowance, the estimated normal time is about 197 seconds and the workflow limit about 293 seconds. These are pre-dispatch limits, not claims that a particular WSL run has passed.

The local loopback JS integration and its diagnostic wrapper passed in 14.3 seconds after this change. The WSL outcome remains unverified. If needed, run only `.venv-nanobot/bin/python scripts/check_gepa_first_failure.py` after `git pull --ff-only`; inspect its saved report and first failure evidence before any release-wide rerun.
