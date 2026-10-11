# Measured Local Skill Evolution — v0.4.0 (本機技能演化)

This release adds an executable, reproducible skill-search loop to the existing Web GUI. The engine is **local-rule-search-v1**, implemented in this repository. It uses deterministic training feedback and four allowlisted text rules. It does not install/call nanobot, GEPA or an LLM. Free-form prompt evolution and the planned `python-fix-and-verify` model runner remain future adapter work.

## Update, inspect and start (更新、環境檢查與啟動)

Stop the old GUI with Ctrl+C, then use the existing D-drive checkout:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --check --python python3.11
bash scripts/start-gui.sh
```

If the doctor reports missing prerequisites, run `bash scripts/install-wsl.sh --python python3.11` before starting. This phase adds no third-party dependencies. Existing `.venv`, registry/demo storage and runtime history are retained. New SQLite tables are created automatically at service startup.

Open `http://localhost:8765/#skills` and press **Ctrl+Shift+R** to load the updated modules. Confirm **v0.4.0** in the sidebar. Use `bash scripts/start-gui.sh --port 9000` and `http://localhost:9000/#skills` if another port is needed. The existing private hosted Site provides the same static UI; actual execution still requires the local same-origin Python server. No remote tunnel, firewall change or model credential is needed.

## First experiment (第一輪實驗)

1. Open **本機技能實驗**. Confirm a successful poll time and active version `S0`.
2. Keep exactly one enabled coordinator, worker, evaluator, reflector and reviewer in the registry. Names/IDs are bound to the workflow; configured framework/model/Skill strings and graph links remain metadata.
3. Select a candidate limit from **1–4** and choose **開始技能演化**. Baseline and data/code hashes are frozen before work starts.
4. Inspect candidate training/validation results, the measured validation curve, Skill body comparison and baseline training failures. **執行監控** shows actual role PIDs, output, timestamps and cancellation. Fast stages may finish between polls; recorded evidence remains available.
5. Review the candidate and evidence. **核准並啟用候選** creates an immutable server-owned local version and changes the active pointer. It stays disabled for unfinished, cancelled, failed, stale, non-improving, already-approved or outdated-baseline runs.
6. Use **試跑使用中的技能** with your own text. A baseline trial of `  Ｓｅｒｖｉｃｅ   Down  ` retains the input; the fully evolved version returns `service down`.
7. Choose **切換至此版本** on `S0` to roll back. Trial output changes immediately on the next request; in-flight experiments retain their frozen version. **↓ SKILL.md** exports the version's generated Markdown.

The previous simulation remains under **演化展示**, **展示評估紀錄** and **展示版本管理**. Browser JSON import/export operates on that simulation and registry, not the server's measured skill versions.

## Skill contract (技能執行契約)

Target: `normalize-support-title`. Its name and description are immutable. A candidate changes exactly one disabled rule to enabled. Rule execution order is fixed:

| Rule | Execution |
| --- | --- |
| `unicode_nfkc` | Unicode NFKC normalization |
| `casefold` | Unicode case folding |
| `trim` | Leading/trailing whitespace removal |
| `collapse_whitespace` | Whitespace sequences become one ASCII space |

`S0` disables all four rules. Each version contains an immutable JSON policy and a generated instruction body with a SHA-256 hash. Validation rejects inconsistent bodies, metadata and hashes. The policy is the executable contract in this release; Markdown export is an integration artifact, not an installed external-agent Skill. Model tools, arbitrary code, commands and uploaded datasets cannot be submitted through this API.

## Evaluation and search (評估與搜尋)

The repository supplies **50 handwritten engineering examples**, split into **20 train / 10 validation / 20 held-out** tasks with distinct IDs and canonical-output groups. These are a small fixed fixture, not a production benchmark. Success is exact equality between an actual executed output and its predefined expected text; no score is synthesized.

The Worker receives training records only. It executes every available one-rule mutation against those records, then selects the one that strictly reduces total Levenshtein distance. Deterministic rule order breaks ties. Search stops at the candidate limit or when no training-loss-reducing mutation remains. Accepted candidates reuse their already-measured training results; all rejected probes are counted and retained.

The Evaluator independently executes validation tasks for the baseline and each accepted candidate. Higher exact-match success wins, then lower distance, then the earlier/smaller candidate. It selects the candidate before evaluating baseline/selected against held-out tasks. Validation/held-out feedback is not fed back into candidate generation. The source dataset is public to the repository owner; separation is an application boundary, not access isolation from a human developer.

An eligible candidate must **strictly improve validation success** and **not reduce held-out success**. The Reviewer recomputes validation and held-out evidence. Approval performs another trusted recomputation and verifies that the experiment's frozen baseline is still active. A completed experiment with no eligible improvement is a valid result and creates no version.

For a four-candidate run from `S0`, measured counts are:

| Phase | Task executions |
| --- | --- |
| Baseline training + every mutation probe | 20 + (4 + 3 + 2 + 1) × 20 = 220 |
| Baseline + four candidates on validation | 5 × 10 = 50 |
| Frozen baseline + selected candidate on held-out | 2 × 20 = 40 |
| Total shown as search/evaluation count | 310 |
| Reviewer verification, shown separately | 90 |
| Approval verification, outside search count | 90 |

Skill trials are separate from experiment metrics. The maximum search has four accepted mutations and ten probes; there are no model token/cost budgets because no model calls occur. Existing 120-second per-role deadlines and process-group cancellation apply. No pause/resume feature is added for real work.

On this fixture, the complete rule policy improves validation **2/10 → 10/10** and held-out **4/20 → 20/20**. This verifies the bounded normalization contract and end-to-end evidence path. It provides no evidence of general LLM-agent performance, learned world knowledge or transfer to Python repair. Repeated use exposes this fixed held-out set; replace/version the dataset before making broader performance claims.

## Roles and evidence (角色與證據)

| Role | Actual task | Artifacts |
| --- | --- | --- |
| Coordinator | Freeze active version, split hashes and code provenance | `skill-config.json`, `skill-manifest.json`, `baseline.md` |
| Worker | Training-only mutation probes and accepted candidates | `search.json`, `training-traces.json`, `training-probes.json`, `candidate-N.md` |
| Evaluator | Validation selection, then held-out comparison | `evaluation.json` |
| Reflector | Rule-based comparison and recommendation | `reflection.json` |
| Reviewer | Trusted recomputation and review gate | `review.json` |

`progress.json` is written atomically after measured work. The same non-overlapping polling client reads progress with subprocess telemetry. There is no artificial execution delay. The graph remains configured intent; actual stage order is fixed, sequential and recorded separately.

## Persistence and concurrency (保存與並行操作)

Everything stays below `/mnt/d/nanobot-gepa-mvp/.local/`:

- `runtime.sqlite3`: runs plus `skill_versions`, `skill_state` and `skill_actions` tables.
- `runs/RUN-<uuid>/`: frozen baseline/config, progress, reports and role logs.
- `tmp/` and `cache/`: launcher-managed scratch and caches.

The local state supports up to **100 immutable versions**. The GUI/API shows ten recent skill runs and twenty recent activation actions; older evidence remains in SQLite/run directories. Back up `.local/` with the server stopped. Markdown export alone does not back up scores, policy, lineage or activation history.

Project-health and skill workflows share one supervisor/one active-run slot. Skill activation uses an `expectedRevision` check so stale browser tabs cannot overwrite newer state. Approval rejects duplicate releases and outdated baseline evidence. A lost submission response can be retried with the original immutable request/body; changed submissions cannot reuse its idempotency key. Browser-imported scores are never trusted.

Graceful shutdown cancels active work. Restart marks unfinished runs interrupted and blocks their approval. Changing the evaluator/runner/runtime source or dataset invalidates unfinished or unapproved old evidence; rerun after upgrades. Existing approved versions can still be activated after their own policy/body hash is checked.

## Next adapter step (後續 Adapter)

Reuse immutable versions, provenance, trusted evaluation, revision checks, polling and human review when adding a nanobot runner and GEPA optimizer. Replace the declarative execution/search boundaries with isolated model-task execution and reflective candidate generation. Pin actual SDK versions, configure credentials server-side, enforce model-call limits and introduce a new dataset/evaluator contract before enabling that mode.
