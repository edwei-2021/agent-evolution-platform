# Skill Generation History (Skill 產生紀錄)

All supported Skill generators retain candidates independently of release approval. The archive covers GEPA Python instructions, LLM title-normalization instructions and local rule-search probes. A new instruction, an unchanged proposal, an unselected candidate and a formally approved version are separate observations.

## Generation records (產生時的紀錄)

Each new attempt writes `.local/runs/RUN-…/skill-audit/IDENTITY.json` before generation and updates it atomically as a response returns, passes validation or fails. Existing attempt identities are not overwritten. An ordinary exception records its type; a terminated process leaves its last saved started/returned snapshot. Authoritative proposal/call artifacts remain separate. Supplementary audit I/O failure does not change scoring, dispatch or release decisions.

| Generator | Identity | Recorded origin |
| --- | --- | --- |
| GEPA Worker | P001, P002, … | Parent Skill, exact training rollout IDs/scores, current metric/global-call use, reflection instructions and optimizer settings |
| LLM Reflector | C1 | Parent Skill, training-failure references and reflection instructions |
| Local rule Worker | T0101, T0102, … | Every probed rule Skill, including unchosen trials; mutation, round and whether chosen for the next step |

Records include original Skill/body hashes, full bounded instruction text, Parent identity, timestamps, component, model/provider/reasoning/output settings, dataset version/hash/revision, frozen limits and relevant code identities. No validation or held-out cases are added to generation feedback. New GEPA searches also save actual perfect-score skips and stopping conditions in `gepa-search-audit.json`; this observes the existing policy without changing its thresholds or random seed.

A generated candidate remains saved even if later evaluation fails, loses selection or never reaches approval. Returned text that fails validation is retained as a failed attempt, without claiming it is an executable or approved Skill. Oversized invalid text keeps its identity and remains available in original local response evidence rather than bypassing preview limits.

## Query and compare (查詢與比較)

Open **Skill 產生紀錄** in WORKSPACE. Filter by Skill type, browse 20 Runs per page, or enter an exact Run ID. The page shows baseline and every saved attempt, generation conditions, training references, before/after instructions, diff, search skips/stopping conditions and formally approved version metadata. A GEPA history button opens its corresponding Run directly. A fresh read does not dispatch models or replay evaluation. Service changes and stale asynchronous responses cannot substitute another Run's records.

The identity is the Run ID plus candidate ID; P001 in two different Runs is not one version. Parent hashes retain lineage even when multiple proposals have identical text. Matching the selected text does not establish which identical proposal was selected, and does not imply approval. Separate GEPA, LLM and rule version stores stay separate.

Older evidence is projected without rewriting original files. Saved proposal/search/probe files can reconstruct lineage and frozen conditions. A bounded saved reflection response can recover instruction text after an interrupted ledger write; that text is labeled **returned / recovered-response**, not validated generation. Unknown times, missing conditions and unrecorded stopping reasons remain unknown. The projection never reads the current mutable question catalog to relabel older evidence.

## Diagnostic export (診斷匯出)

The existing **下載診斷包** now includes `skills/RUN-….json` using the same projection as the query page. This is an explicit Skill-artifact section: full redacted instruction text, Parent, diff and generation conditions are included; raw task prompts, source, expected answers, full model requests/responses and credentials remain excluded. It does not apply the generic log's 1000-character/depth truncation to Skill text. Known credential formats are redacted; original hashes and exported-text hashes are distinct.

Default export scans up to 1000 historical Skill Runs, rather than only the ten recent status records. Logs reserve 8 MiB of the existing 32 MiB file-input budget for Skill evidence. Skill JSON output is capped at 8 MiB. Limits, missing/corrupt evidence and omitted Runs are explicit in each projection's warnings or the export manifest. Included counts can contain partial previews; inspect warnings before claiming complete history. These export limits do not delete the original local records.

Use **下載此 Run 診斷包** to collect one older Run independently of the default archive's aggregate limit. CLI equivalent:

```bash
python3 scripts/export_diagnostics.py --run-id RUN-your-run-id
```

Local read-only endpoints, protected by the existing localhost/origin boundary:

- `GET /api/v1/debug/skills?offset=0&task=gepa-evolution`
- `GET /api/v1/debug/skills/RUN-…`
- `GET /api/v1/debug/support?runId=RUN-…`

Each detail preview uses an 8 MiB file-read ceiling, at most 32 generation attempts and bounded instruction text. Symlinks, unsupported task types and invalid identities/queries are rejected. Local query/export never imports an optional SDK, starts a new experiment or recomputes scores. Records remain in local run storage without automatic pruning; manual deletion is outside retention guarantees.

## Verification (驗證)

Focused tests cover unchanged/unselected/failed candidates, interrupted response recovery, refused overwrite, read-only behavior, redaction through the actual ZIP consumer, history older than ten Runs, approved-version metadata, pagination, input bounds, origin enforcement and stale replies. Actual pinned GEPA/nanobot SDK workflows with scripted loopback responses check both generation and perfect-score skips; separate real subprocess LLM and rule workflows check failure capture and every unchosen rule probe. Original repair/evaluation/approval/tamper gates and model-call counts remain intact. This validates implementation behavior, not a new Windows/GPU evolution gain or broad M7 acceptance.

Validation for this change: 8 archive/API cases, 13 diagnostic cases, 12 existing read-only history cases, 61 focused frontend cases and five exact subprocess/SDK integration cases passed. Ruff, the staged source credential-pattern scan and diff checks passed.
