# Phase M unattended test matrix (自動測試矩陣)

`scripts/check_m_matrix.py` is the source-owned unattended entry point. The GitHub Actions push/PR workflow installs locked Python and Node dependencies, builds the real Docker evaluator image, starts this script without stdin, and uploads `phase-m-matrix-support`. The local GUI at `http://localhost:8765/#matrix` can also start this program via the **完整自動測試** page. One click starts a supervised background job; browser navigation or closure does not stop it. The page polls persisted progress, offers cancellation and downloads its support ZIP. It requires the locked M Python dependencies and automatically builds the Docker evaluator image with an 1800-second bound. Docker preparation failure is retained in the summary, log and ZIP; no model requests are dispatched by preparation. `--list-plan` previews the matrix without dispatch.

## Scope and acceptance rule (範圍與判定)

| Flow | Variant coverage in each round | Required rounds | Completion evidence |
| --- | --- | ---: | --- |
| Configurations | Canonical ledger enabled/disabled × GEPA `profile` smoke/full/bank × `searchMode` omitted/standard/explore × `finalRepetitions` omitted/1/2/3: 72 exact paths (45 accepted, 27 rejected as specified), plus a separate negative guard | 3 | All 73 exact pytest cases passed; no missing combination or skip |
| Other options | LLM profile smoke/full × timeout omitted/10/3600, rule Skill candidates 1–4, Python repair duration 60/7200 × timeout 10/3600 × call budget 2/12: 18 paths | 3 | All 18 exact pytest cases passed; no missing combination or skip |
| Components | M1–M7 component tests, including release/Git publication failures, role boundaries and M5 dataset checks | 3 | Pytest passes; at most the explicitly component-only M4 Docker skip |
| Acceptance | Complete M1–M7 plan, Docker isolation, pinned nanobot/GEPA loopback workflows, GUI canonical one- and three-pass final comparison, release replay/rollback and M7 static checks | 3 | Seven passed stage checks from the same source hash, plus one unscoped nested release report with every step completed and no skipped case |

The runner also compares its workflow catalog with the five task types accepted by `RuntimeService.start`: project health, rule Skill evolution, LLM Skill evolution, nanobot repair and GEPA evolution. Each acceptance round must contain a nonempty passing release test module for each. Separate evidence requirements cover the Ollama/Strata provider paths and V2/V3 challenge workflows; V3's catalog module checks all five published batches. `summary.json` records `coverage.workflowPasses` for these eight named categories (three required each), and the Web UI displays their counts. Adding a runtime task without updating this catalog fails immediately; an omitted or empty release test module prevents certification.

The 72 GEPA paths and 18 other option paths call their production `freeze` entry points with frozen provider and SDK availability. They verify counts, budget arithmetic, policy, exploration seed, omitted defaults and selected repeat setting without model dispatch. The rejected paths explicitly require the canonical ledger before SDK/model inspection. Full acceptance runs execute the existing scripted loopback model and pinned SDK. The nested release report must include the exact dynamically expanded source-owned step manifest, and every step must complete in all three rounds. Tests do not claim real Windows/Ollama/GPU behavior or optimizer-internal crash resume. Numeric budgets, arbitrary challenge-bank contents, external model providers and hardware configurations form unbounded spaces and are covered by boundaries/representative test cases, not an exhaustive Cartesian execution. Each declared path is executed at least three times when the matrix passes; an interrupted or blocked matrix is explicitly **incomplete**.

The source commit and source inventory hash are frozen before round one and checked before every attempt. The runner does not retry a failed command: it stops and records all unexecuted flow/round pairs. This avoids repeating a known failed upstream model workflow simply to satisfy a numerical repetition target. The next development iteration starts from that first failed leaf and its evidence.

## Saved records (保存紀錄)

Every invocation creates a new `.local/m/matrix/MATRIX-…/` directory:

| File | Contents |
| --- | --- |
| `summary.json` | Exact command/flow/round, source identity, timestamps, pass/fail, configuration IDs, M stage outcomes, per-workflow passing round counts, nested release step/case counts, omissions and environment limit |
| `events.jsonl` | Process start/finish and attempt/whole-matrix terminal decisions |
| `{flow}-round{N}.log` | Redacted terminal stream, bounded to its last 4 MiB |
| `support.zip` | The summary/events/logs, all available M1–M7 stage JSON and redacted nested release reports, with a size/omission manifest |

The workflow uploads the ZIP and summary even after failure. GUI jobs are recorded under `.local/m/matrix-control/MAT-…json` with a bounded worker log and the same matrix directory as the CLI. `GET /api/v1/tests/matrix/{id}/support` downloads the completed ZIP; `POST /api/v1/tests/matrix` starts the entire plan and `POST /api/v1/tests/matrix/{id}/cancel` cancels it. Mutation requires the existing local session token and the server remains bound to loopback; use a trusted localhost tunnel to reach it from another device. A successful M gate does not generate its own support ZIP, so the matrix packages its stage reports. The original M gate may additionally save a failure support ZIP under `.local/m/support/`; GitHub Actions uploads that directory separately. Logs exclude raw model bodies by using the existing redaction policy and size bounds. The matrix status is `passed` only if all four flows complete three rounds; otherwise `summary.json` identifies the first failure and every omitted round. A green matrix certifies this specified CI/loopback scope, not the remaining Phase M product closure or a real GPU run.
