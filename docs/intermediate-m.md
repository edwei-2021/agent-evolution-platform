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

Rollback targets the current release's approved parent and requires the current pointer revision. Activation changes future snapshots, not in-flight manifests or historical evidence. This new release pointer does not silently change the legacy rule/LLM/GEPA active pointers. Final production cutover and Git reconciliation remain separately gated.

Back up the stopped service's entire .local/m (DB, CAS, signing key) and existing .local data. backup-db can produce a transactionally consistent DB copy but is not a complete artifact/key backup by itself.

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

The probe retains the original 20-second workflow test expectation, uses only a loopback mock model, and bounds the test harness to 120 seconds. Its report and test log are stored under .local/test-reports/LLM-CHECK-...; on failure it also captures role states/log tails, mock request count and periodic Python thread stacks. These distinguish process startup, progress I/O, lock waits and model transport. A timeout is not silently converted to a pass.

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

The measurement compares current single-record writes with one batch on the actual project filesystem, including final close/checkpoint. Both paths must retain the same record count. It sends no model requests and does not measure the pre-fix FULL policy or predict GPU speed. If the single-case probe remains failed, inspect the new state/thread logs instead of raising the test deadline.
