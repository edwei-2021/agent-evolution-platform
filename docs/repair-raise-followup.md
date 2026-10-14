# Repair Exception Syntax Contract (修復例外語法契約)

Updated: 2026-10-15. This public record describes the defect, repository-owned regression fixtures and aggregate local verification. Uploaded run identifiers, model/provider metadata, original candidate payloads and attachment hashes are excluded. The original incident files remain part of the private diagnostic input.

## Cause and correction (原因與修正)

A real model generated a valid repair using `raise ValueError`. The trusted AST validator accepted only the constructed form `raise ValueError(...)`. Its error, `Only raise ValueError is permitted`, described the very syntax it rejected. Rejected writes left the baseline unchanged; subsequent visible tests therefore continued to fail, and repeated correction attempts eventually exhausted the SDK iteration cap.

The shared policy now accepts either the trusted ValueError class or a permitted ValueError instance. It still rejects other exception classes, bare re-raise, explicit exception chaining, attributes, keyword arguments and trusted-builtin reassignment. Source/node limits, available tools, call caps, workflow deadlines and independent scoring remain enforced. The error now names both accepted forms and the prohibition on chaining.

No failed historical run is relabeled completed. Validating an old candidate offline cannot replace the original execution trace. A fresh target-model run remains necessary to establish behavior after deployment.

## Maintenance lesson (維護經驗)

The repair mock, grouped GEPA reference sources and Docker happy-path fixture all used constructed exceptions. The suite covered one valid representation while omitting an equally valid class form promised by the task wording. A real model exercised that missing form.

The recurring gap is an incomplete executable contract. Syntax acceptance requires semantic variation (語意等價變體), in addition to lifecycle and timing proofs. Follow the first failed tool and its persisted file effects before interpreting the terminal SDK error. Model-facing policy feedback must accurately describe the grammar and an actionable accepted form.

Repair the shared policy rather than teaching only the mock to emit parentheses. Write mediation, independent evaluator, reviewer replay, GEPA and packaged image payload must agree. Preserve iteration limits and independent score computation.

## Verification and shared-path audit (驗證與共用路徑)

The new exception-class regression fails on the old validator with its contradictory message. After correction:

| Check | Result |
| --- | --- |
| Class, empty-constructor and message-constructor exception forms | Visible and hidden splits passed |
| Other exception types, re-raise, chaining, attributes, keyword arguments and builtin shadowing | Rejected |
| Existing imports/attributes/loops/recursion/large-expression defenses | Remain rejected |
| Full grouped GEPA dataset's 15 exception-bearing tasks | 30 evaluation jobs, 90/90 task checks passed |
| Actual nanobot 0.3.5 SDK with a class-form fixture | Completed in 4 calls / 3 tools within unchanged budget 8 |
| Independent evaluation and reviewer replay | Visible 6/6, hidden 6/6; evidence revalidated; provider slot released |
| Absolute dispatch-cap regression | Passed; repeated reads still stop at their frozen cap |
| Staged evaluator image files under `python -I -S` | Both splits pass; explicit chaining rejected |
| Existing Docker command isolation flags | Passed |
| Focused automated tests | **8 passed, 0 skipped**; four unrelated M4 cases explicitly deselected |
| Ruff on the four affected Python files | Passed |

`repair_fixture.validate_source` is shared by write mediation, the isolated evaluator and evidence replay. The Docker image copies this module and evaluator; the M runner uses that image. GEPA uses the same runner/evaluator for exception-bearing clamp, span and clipped-sum families. Their class-form variants are covered without repeating the optimizer search.

The local SDK proof uses loopback scripted responses. Docker is unavailable locally; staged-file execution checks the image payload, and the Docker-enabled acceptance case now includes both exception forms. This does not qualify a rebuilt Docker image or a new target-model workflow on the user's machine. Public case names, source hashes and aggregate results are in the [verification ledger](verification/repair-raise-followup.json).

## Operator next step (操作方式)

For GUI repair, stop the GUI and update the existing checkout:

```bash
cd /mnt/d/agent-evolution-platform
git pull --ff-only
bash scripts/start-gui.sh
```

Refresh `http://localhost:8765/#repair`, retain the existing provider settings and call budget, and submit one new repair run. Existing warmup can be reused while the model remains resident. No dependency installation or broad M7 rerun is required for this diagnosis.

For Docker-backed `scripts/run_m_repair.py`, rebuild the evaluator payload so the image contains the corrected validator:

```bash
docker build -f infra/m/evaluator.Dockerfile -t aep-evaluator:m .
```

The runner resolves the immutable image ID for the new experiment. Keep an old image's policy failure distinct from model-quality evaluation; preserve the no-host-fallback rule.
