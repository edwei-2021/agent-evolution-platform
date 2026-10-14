# Selectable M Test Starts (階段與步驟選單)

Use the existing M checker to choose where testing begins. The selected position and every later step run in the original order; earlier work is omitted, without being marked passed. No previous support ZIP is needed for manual selection.

```bash
.venv-m/bin/python scripts/check_m.py --interactive
```

In a terminal, the existing `--profile acceptance` command also opens this menu automatically. Enter the displayed number. `0`, `q`, Ctrl-C or end-of-input cancels before test dispatch. Invalid input asks again and never falls back to a full run.

## Selection flow (選擇流程)

1. Choose a stage: M1 through M7, with a short description.
2. Choose its original, one-based step number.
3. If choosing **M7 step 5**, choose the release starting module.
4. If choosing a Python module, choose its starting test case. Earlier cases in that module are omitted.

For the previously failed GEPA perfect-seed case, choose **M7 → step 5 → `python-gepa_test` → `test_perfect_seed_skips_proposals_and_cannot_release_without_improvement`**. The current source lists it as case 11. Read the displayed case name rather than relying on a historical module/case number.

| M7 step | Menu label | Work |
| ---: | --- | --- |
| 1 | API 與安全性 | API authorization, worker and replay checks |
| 2 | 監督器與接續選單 | Gate supervision and selection contracts |
| 3 | 原始碼掃描 | Source safety scan |
| 4 | SDK 環境檢查 | Pinned SDK prerequisites |
| 5 | Release 回歸 | Source-owned release modules; optional starting case |
| 6 | Ruff 檢查 | Python static checks |
| 7 | TypeScript 檢查 | Strict contract type checks |

Choosing M7 step 6 runs only steps 6 and 7. Choosing an earlier stage continues through its remaining steps and all later stages. Failure still blocks dependent steps.

## Preview and unattended use (預覽與無人值守執行)

List the stage/step menu without running tests:

```bash
.venv-m/bin/python scripts/check_m.py --list-steps
```

Preview a selection without running tests or creating acceptance records:

```bash
.venv-m/bin/python scripts/check_m.py --interactive --dry-run
```

Start directly from M7 step 6:

```bash
.venv-m/bin/python scripts/check_m.py \
  --from-stage M7 --from-step 6 --non-interactive
```

Start directly from the failed GEPA case:

```bash
.venv-m/bin/python scripts/check_m.py \
  --from-stage M7 --from-step 5 \
  --release-step python-gepa_test \
  --from-case gepa_test.GepaWorkflowTests.test_perfect_seed_skips_proposals_and_cannot_release_without_improvement \
  --non-interactive
```

CI and setup explicitly pass `--non-interactive`. With redirected input and no explicit interactive option, the original full acceptance path remains unattended. Start selection is available for the acceptance profile; the separate components profile retains its existing meaning. `--from-step` requires `--from-stage`; module/case selection requires M7 step 5. Unknown modules, unknown cases and mismatched module/case pairs fail before test dispatch.

## Execution and evidence (執行與證據)

- The plan is rebuilt from current source. Menu values never become shell commands.
- Required filesystem calibration precedes a selected release tail, even if its historical position was earlier. It sends no model requests.
- SDK/version checks still run when the release child validates dispatch. Selecting a late static-only step does not run earlier SDK or Docker checks.
- GEPA retains its exact-case supervisors and frozen workflow/replay/cleanup budgets. Selected release steps share the existing workload calibration.
- Progress and report `command_index` retain the original stage numbering: a start at M7 step 5 reports `5/7`, `6/7`, `7/7`.
- Reports retain `startStage`, `startStep`, selected module/case, omitted commands/cases and source hashes. A successful partial run is `scoped_passed`, not full M acceptance; it does not write complete-stage acceptance rows into `/api/m/checks`.
- Failure ZIPs include the same scope and existing nested evidence. The support-based `check_m7_remaining.py` command remains available for exact failure recovery.

## Local verification (本機驗證)

Selection and gate tests passed **38/38**; existing workload/calibration contracts passed **8/8**, support-based resume contracts **9/9**, and the quick/release profile guard **1/1**. A real terminal preview also exercised the default numbered menu. New selection contracts cover numbered choices, invalid/empty/cancelled input, TTY/CI behavior, previews, exact omissions, preserved indices, partial acceptance isolation, failure propagation and support export. A real CLI run selected only warmup's final restart case, then Ruff and strict TypeScript; it passed as `scoped_passed` in `MCHECK-0a6ba7a830a74c7c9e4ecfca8ff036d9`. No GEPA workflow or M1–M6 execution was needed for this verification.

The audit caught and fixed executable classification: Ruff lists `scripts/check_steps.py` as a source argument, which must not activate the nested release protocol. Detection now checks the executed script, with a dedicated regression and real Ruff continuation proof. An existing positive streaming/continue fixture also hit its one-second aggregate cap once; the exact unchanged rerun passed. Its purpose is now tested with deliberate startup beyond one second and a separate bounded fixture allowance. The negative hard-limit fixtures and all production deadlines remain unchanged.

These checks validate local selection/supervision behavior. They do not certify full M or WSL integration acceptance.
