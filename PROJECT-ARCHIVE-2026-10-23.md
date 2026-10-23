# Project archive and restart snapshot — 2026-10-23

This is the entry point for restarting Agent Evolution Platform (代理人演化平台). Development is paused at the user's request. This snapshot records observed implementation, evidence, and open work; it is not a Phase M completion certificate. The archive commit containing this document is the source snapshot. Start by checking that commit and the linked CI run rather than treating a later moving `main` branch as identical evidence.

## Identity and evidence cutoff

| Item | Snapshot |
| --- | --- |
| Repository | `edwei-2021/agent-evolution-platform`, public GitHub repository, default branch `main` |
| Source base inspected | `7252eae3d8473c3b13e31ed9c70551bf51b78246` (`Split V3 batch workflows under independent release budgets`) |
| Date | 2026-10-23 UTC; CI status below was inspected during archive preparation and can change afterward |
| Product baseline | Legacy GUI/runtime v0.7.1 with additive Intermediate Phase M services; see the [revised plan](docs/agent-evolution-platform-development-plan.md) and [M guide](docs/intermediate-m.md) |
| Latest source CI | [GitHub Actions run 39915859416](https://github.com/edwei-2021/agent-evolution-platform/actions/runs/39915859416) for `7252eae`: `components` job still **in progress** at matrix step when inspected. No terminal verdict or three-round acceptance was available. Check its final result and artifact before new testing. |
| Last completed matrix evidence inspected | [Run 39914559202](https://github.com/edwei-2021/agent-evolution-platform/actions/runs/39914559202), source `c6ba8f18ee55d87e46887955fcd32c718d312ded`, artifact `phase-m-matrix-support`, summary under `matrix/MATRIX-1389f8a91e264680a0fe8fa36488a637/summary.json`. This is evidence for that earlier source only. |

The repository's versioned source, tests, plan, catalog, and this document are archived by Git. `.local/` runtime databases, user model settings, candidate bodies, private tokens, diagnostic bundles and Windows/WSL environment are not in the Git source snapshot. Preserve those separately if historical Runs or reproducibility on the user's machine matter; do not commit secrets or raw prompts/responses.

## What exists

- Legacy local Web UI, persisted Ollama/Strata settings, preloading, logs, Python repair, rule/LLM Skill experiments and GEPA Skill-body evolution. Candidates and approvals are distinct. [Skill generation history](docs/skill-generation-history.md) describes generator identity, parentage, unchanged/failed attempts, version differences and read-only export.
- M1–M7 additive code: compatibility migration, Pydantic contracts, durable local queue/evidence, Docker evaluator, dataset/comparison, signed releases with local Git publication, FastAPI facade, CI and support bundles. The [M guide's implementation table](docs/intermediate-m.md#1-delivered-programs-by-step-各步驟程式) lists programs and closure gaps. Having the code does not mean the phase exit criteria passed.
- V3 repair catalog contains **60 designed tasks**: 20 easy, 20 medium and 20 hard, in five disjoint balanced batches of 12. Design difficulty is not measured model difficulty. See [V3 catalog](docs/python-challenges-v3-catalog.md).
- A Web UI page at `http://localhost:8765/#matrix` starts and monitors the unattended [Phase M matrix](docs/phase-m-matrix.md). Its four flows each require three rounds. The finite catalog has 103 paths (72 GEPA configuration, 18 other options, eight workflow/provider, five V3 batches), minimum reported path coverage 60%, and separately requires complete three-round flows, all five V3 batches and all 60 actual scripted-model question IDs. This catalog excludes arbitrary inputs, custom providers/datasets and physical GPU behavior. `--list-plan` previews without dispatch.
- Target architecture in the [revised plan](docs/agent-evolution-platform-development-plan.md) is two isolated evolution loops: GEPA changes a Skill body under a fixed workflow; future OpenEvolve changes a declarative workflow under approved Skills. The second loop is planned, not a delivered capability.

## Last concrete evidence and blocking point

The completed `c6ba8f1` matrix recorded configurations **3/3**, other options **3/3**, and components **3/3**, followed by acceptance **0/3**. Its partial finite-path coverage was **90/103 = 87.38%**, but actual V3 scripted-model questions were **0/60** and V3 batches **0/5**. Acceptance round 1 passed M1–M6 and initial M7 checks, then M7 release preflight raised `ValueError: Integration manifest changed; audit every added workflow`; acceptance rounds 2 and 3 never started. Thus 87.38% is partial path accounting, not a successful acceptance or demonstrated evolution gain.

Commit `7252eae` split the two V3 workflows into independently supervised release steps, updated the release manifest and frozen budgets, and passed focused local checks (24 tests and Ruff recorded in the development handoff). Its full CI matrix was still running at the cutoff above. **First action on restart:** inspect run 39915859416's terminal status and `phase-m-matrix-support` summary/ZIP. If it failed, use its first failed leaf case and source identity; do not rerun passed upstream model work merely to discover the same problem.

The user's earlier Windows 10 reboots during Strata workloads have no confirmed root cause in this source snapshot. A standalone FurMark workload and later Ollama execution did not reproduce the reboot, but neither isolates software, driver, power and model concurrency contributions. Scripted loopback SDK checks do not establish Strata/Ollama improvement, GPU stability, real Windows performance or host-specific Docker correctness. [Maintenance lessons](docs/ai-maintenance-lessons.md) document deadline, supervision and diagnostic pitfalls. Avoid turning this observation into an unverified hardware conclusion.

## Phase M closure status

**Open.** M1–M7 component implementation and some historical focused/WSL stage passes exist, but no full three-round acceptance on the archived source was established at this cutoff. Also outstanding beyond a green CI matrix:

| Area | Remaining decision or evidence |
| --- | --- |
| M1–M3 | Validate migration/restore on the actual WSL checkout, wider real task/runtime capabilities, and how historical legacy data relates to the new additive ledger. |
| M4–M5 | Prove Docker isolation on the target host and real GPU comparison with approved candidate provenance and selection. The evaluator's bounded pure-function scope does not establish arbitrary repository isolation. |
| M6 | Optimizer-internal GEPA search resume and remote release publication are open; local Git reconciliation and checkpoints do not prove those capabilities. |
| M7 | Complete CI/image and WSL service verification, full GUI/RBAC migration and browser regression. |
| Product goal | Measure repeated baseline/candidate quality on a frozen representative task set and independent held-out tests. More candidate bodies or higher matrix path coverage alone do not prove beneficial evolution. OpenEvolve workflow evolution and additional runtimes remain later phases. |

The precise M exit criteria are in the [development plan](docs/agent-evolution-platform-development-plan.md#5-intermediate-phase-m--required-missing-work-中間階段待補做項目). Do not promote a component pass, one scoped M7 continuation, a previous commit's evidence, or an in-progress CI run to completion of the current source.

## Restart procedure for the next maintainer

1. Read this file, `AGENTS.md`, [AI maintenance lessons](docs/ai-maintenance-lessons.md), [M guide](docs/intermediate-m.md), [matrix contract](docs/phase-m-matrix.md) and the CI run linked above. Confirm `git rev-parse HEAD`, branch, `git status`, lockfiles and whether later commits changed the archived source.
2. Retrieve the latest CI matrix artifact and read `matrix/MATRIX-*/summary.json` first. Confirm `sourceCommit`, `sourceHash`, `status`, `coverage.flowPasses`, `coverage.modelQuestionsCovered`, `coverage.missingPaths`, `attempts`, stage reports and the first failed release step/case. CI artifact retention is finite; save the ZIP separately if long-term evidence matters.
3. If CI failed, inspect the named first leaf in its nested support ZIP/log. Follow [M7 scoped continuation](docs/intermediate-m.md#m7-failure-recovery-and-ai-maintenance-失敗接續與維護經驗) where applicable, then validate affected dependencies and the remaining tail. A scoped pass is not full acceptance. If CI passed, record its exact source and scope, then tackle the outstanding target-host and product-quality gates in the table above.
4. On the operator's machine, back up the stopped checkout, `.local/` databases and Run directories, selected diagnostic/support ZIPs and relevant environment configuration securely before migration or an expensive rerun. The GUI's **下載診斷包** / per-Run export and the matrix's **support ZIP** serve different evidence purposes. Do not archive `.local/m/operator.token`, API credentials or raw model responses in public GitHub.
5. Use the [operator guide](docs/intermediate-m.md) to install pinned dependencies and build the evaluator on a Docker-capable host. Check the matrix plan without dispatch using `.venv-m/bin/python scripts/check_m_matrix.py --list-plan`; after analyzing existing evidence, the GUI page or `.venv-m/bin/python scripts/check_m_matrix.py` can run the full plan. Keep source and dataset frozen during a run. Failed runs emit a `support.zip` and preserve omitted rounds.
6. Before editing stage acceptance, timing, SDK discovery or Skill history, honor `AGENTS.md`; audit the expanded leaf-test manifest and both child and parent deadlines. Keep observed facts, hypotheses and proposed fixes distinct. Do not weaken release gates or claim an evolution benefit from synthetic/scripted tests alone.

## Evidence and source map

| Need | Entry point |
| --- | --- |
| Product scope, exit criteria and later phases | [Revised development plan](docs/agent-evolution-platform-development-plan.md) |
| Implemented M parts, commands and historical failures | [Intermediate M operator guide](docs/intermediate-m.md) |
| Unattended three-round flows and coverage semantics | [Phase M matrix](docs/phase-m-matrix.md), `scripts/check_m_matrix.py`, `.github/workflows/` |
| Failure triage and test supervision rules | `AGENTS.md`, [AI maintenance lessons](docs/ai-maintenance-lessons.md), `scripts/check_m.py`, `scripts/check_m7_remaining.py` |
| Skill identities, generated versions and approvals | [Skill generation history](docs/skill-generation-history.md), [Workload/change history](docs/gepa-workload-and-change-history.md) |
| Task set and difficulty/split design | [60-question V3 catalog](docs/python-challenges-v3-catalog.md) |
| Local evidence | `.local/runs/`, `.local/m/matrix/`, `.local/m/support/` on the operator's machine; GitHub Actions run artifacts for CI |

This document deliberately freezes a knowledge handoff, not a claim that the project converged. Preserve the exact archive commit SHA and download its GitHub source ZIP when a standalone source package is needed.
