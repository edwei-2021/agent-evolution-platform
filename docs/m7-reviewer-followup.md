# M7 Reviewer Follow-up Verification (審查重播驗證)

Updated: 2026-10-14. Environment: local Linux, real pinned nanobot-ai 0.3.5 and GEPA 0.1.4, loopback model fixture. Original input: the terminal transcript for `MCHECK-217adc0bacc24977bb47f06ca2916115` / `CHECK-2e7c23d60d19420997702b39a8f26d33`; its current support ZIP was not attached.

## Outcome and scope (結果與範圍)

The failed perfect-seed case passes with a 410-second controlled reviewer delay: case duration **491.321 seconds**, 17 rollouts, 68 requests and **51 trusted verification batches**. It also passes normally on the finalized supervisor in **61.889 seconds**. The previously unexecuted optimizer/approval case passes in about **64 seconds**, with 18 rollouts, 54 workflow verification batches and **126 total batches after four additional approval-related replays**.

The first scoped tail passed **146 cases**, then caught a new warmup publication/slot-release race. Its failed report is preserved, not relabeled successful. The next continuation selected only warmup and the remaining guards: **6/6 cases passed**, source scan, Ruff and strict TypeScript passed. A separately added real-worker/controlled-clock case also passed. This chain covers **153 distinct tail case IDs**. Eight workload/scope/calibration contracts and two focused monitor-estimate contracts passed separately, with zero skips.

The ten earlier passed GEPA integration cases and M1–M6 were omitted. Completed modules were not repeated after the warmup failure. Warmup success/failure/cancellation/restart, temporary-file cleanup and provider-slot release remain checked. The native runtime integration retains its required internal health-check dependencies; no extra standalone frontend/API acceptance rerun was added. The source scan is a direct guard for the changed M gate code, rather than a claim that its earlier precheck was unexecuted.

## Failed-step procedure and common cause (失敗流程與共同核心)

Read [AI Maintenance Lessons](ai-maintenance-lessons.md) for the operation table and accountability. Three different errors shared the same weak completion model:

1. Workload estimates did not enumerate immediate verification, evaluator replay and reviewer replay; tests merely asserted a larger timeout.
2. Parent and child independently recalibrated, so their frozen budgets could differ. One development attempt was stopped on discovering that mismatch; it is excluded from pass evidence.
3. Warmup published completion before logging, temporary-file cleanup and provider-slot release. A paused finalizer reproduced this deterministically on old code in 0.864 seconds.

The repair uses named resource counts, a shared frozen calibration, exact-case parent containment and Windows-safe filenames. Warmup keeps `RUNNING` visible while finalization is paused, then serializes terminal persistence/slot release with status reads. A separate clock test observes a real HTTP dispatch before advancing the deadline and verifies that the real worker is reaped with no retry. Production inference defaults are unchanged.

## Tail results (逐步結果)

| Step | Cases | Seconds | Outcome |
| --- | ---: | ---: | --- |
| `GEPA: test_perfect_seed_skips_proposals_and_cannot_release_without_improvement` | 1 | 491.901 | Passed |
| `GEPA: test_real_optimizer_runner_final_isolation_approval_rollback_and_tamper_gate` | 1 | 64.338 | Passed |
| `journal_batch_test` | 3 | 0.318 | Passed |
| `llm_test` | 17 | 52.869 | Passed |
| `llm_transport_test` | 6 | 0.414 | Passed |
| `m7_resume_test` | 9 | 1.313 | Passed |
| `native_checks_test` | 7 | 3.079 | Passed |
| `ollama_test` | 8 | 5.059 | Passed |
| `polling_boundary_test` | 3 | 0.235 | Passed |
| `repair_test` | 12 | 205.028 | Passed |
| `runtime_test` | 13 | 65.822 | Passed |
| `sdk_runtime_probe_test` | 13 | 18.465 | Passed |
| `setup_orchestrator_test` | 9 | 1.328 | Passed |
| `setup_test` | 16 | 1.219 | Passed |
| `skill_test` | 13 | 24.813 | Passed |
| `step_trace_test` | 10 | 2.922 | Passed |
| `trace_journal_reuse_test` | 2 | 0.568 | Passed |
| `validation_wait_test` | 3 | 0.370 | Passed |
| Warmup continuation | 6 | 6.688 | Passed after lifecycle repair |
| Warmup controlled clock | 1 | 1.667 | Passed; real worker reaped, one request |
| M source scan / Ruff / strict TypeScript | — | 0.658 / 0.201 / 4.322 | Passed |

## Evidence identity and limits (證據身分與限制)

| Evidence | Identity | Meaning |
| --- | --- | --- |
| Controlled GEPA + original tail | `CHECK-d7ca0a4ca6d74970817497323fe8509b` | GEPA and 146 cases passed; warmup failed |
| Final supervisor, exact failed case only | `CHECK-ac3ca98ab599466d9ebb28fb3a699033` | Normal perfect-seed case passed on finalized supervisor |
| Warmup-only recovery + remaining guards | `CHECK-1611116549e74bc0b330dba5ade29e8d` | Completed; preceding 146 cases omitted |
| Machine-readable ledger | [m7-reviewer-followup.json](verification/m7-reviewer-followup.json) | Preserves report hashes, source snapshots, exact case IDs and targeted proofs |

The reports retain their own source inventories. During the controlled run, final preflight/filename/outer-manifest guards were finalized and checked by the focused contracts; the final supervisor then received a separate normal real-case run. The later warmup fix has its own scoped report and clock proof. Documentation was updated afterward. These are scoped results across explicitly identified snapshots, **not a same-source full M7 or phase M pass**. WSL D-drive performance and the precise operation behind the supplied timeout remain unqualified by this local run.

## Target continuation command (目標環境接續指令)

After pulling this repair, the user's existing failed support ZIP selects only the failed GEPA case and unexecuted tail:

```bash
.venv-m/bin/python scripts/check_m7_remaining.py \
  --previous-support /mnt/d/agent-evolution-platform/.local/m/support/MCHECK-217adc0bacc24977bb47f06ca2916115/support.zip
```

If a new failure occurs, use its newly emitted support ZIP; the continuation trims all previously completed tail steps. Do not restart full M acceptance for this diagnosis.
