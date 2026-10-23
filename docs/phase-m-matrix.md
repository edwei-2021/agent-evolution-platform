# Phase M unattended test matrix (自動測試矩陣)

`scripts/check_m_matrix.py` is the source-owned unattended entry point. The GitHub Actions push/PR workflow installs locked Python and Node dependencies, builds the real Docker evaluator image, starts this script without stdin, and uploads `phase-m-matrix-support`. No operator has to start an experiment or make a continuation decision. Run it locally with `.venv-m/bin/python scripts/check_m_matrix.py` only when the same dependencies and Docker are available. `--list-plan` previews the exact matrix without dispatch.

## Scope and acceptance rule (範圍與判定)

| Flow | Variant coverage in each round | Required rounds | Completion evidence |
| --- | --- | ---: | --- |
| Configurations | GEPA `profile` smoke/full/bank × `searchMode` omitted/standard/explore × `finalRepetitions` 1/3: 18 combinations, plus rejection of three repetitions without the canonical ledger | 3 | All 19 exact pytest cases passed; no missing combination or skip |
| Components | M1–M7 component tests, including release/Git publication failures, role boundaries and M5 dataset checks | 3 | Pytest passes; at most the explicitly component-only M4 Docker skip |
| Acceptance | Complete M1–M7 plan, Docker isolation, pinned nanobot/GEPA loopback workflows, GUI canonical one- and three-pass final comparison, release replay/rollback and M7 static checks | 3 | Seven passed stage checks from the same source hash, plus one unscoped nested release report with every step completed and no skipped case |

The 18 configurations are actual calls to GEPA's production `freeze` path with a frozen bank, provider and SDK availability. They verify counts, budget arithmetic, policy, exploration seed and selected repeat setting without model dispatch. Full acceptance runs execute the existing scripted loopback model and pinned SDK; tests do not claim real Windows/Ollama/GPU behavior or optimizer-internal crash resume. Each combination is executed at least three times when the matrix passes; an interrupted or blocked matrix is explicitly **incomplete**.

The source commit and source inventory hash are frozen before round one and checked before every attempt. The runner does not retry a failed command: it stops and records all unexecuted flow/round pairs. This avoids repeating a known failed upstream model workflow simply to satisfy a numerical repetition target. The next development iteration starts from that first failed leaf and its evidence.

## Saved records (保存紀錄)

Every invocation creates a new `.local/m/matrix/MATRIX-…/` directory:

| File | Contents |
| --- | --- |
| `summary.json` | Exact command/flow/round, source identity, timestamps, pass/fail, configuration IDs, M stage outcomes, nested release step/case counts, omissions and environment limit |
| `events.jsonl` | Process start/finish and attempt/whole-matrix terminal decisions |
| `{flow}-round{N}.log` | Redacted terminal stream, bounded to its last 4 MiB |
| `support.zip` | The summary/events/logs, all available M1–M7 stage JSON and redacted nested release reports, with a size/omission manifest |

The workflow uploads the ZIP and summary even after failure. A successful M gate does not generate its own support ZIP, so the matrix packages its stage reports. The original M gate may additionally save a failure support ZIP under `.local/m/support/`; GitHub Actions uploads that directory separately. Logs exclude raw model bodies by using the existing redaction policy and size bounds. The matrix status is `passed` only if all three flows complete three rounds; otherwise `summary.json` identifies the first failure and every omitted round. A green matrix certifies this specified CI/loopback scope, not the remaining Phase M product closure or a real GPU run.
