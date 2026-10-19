# Skill Generation History (Skill 產生紀錄)

## Failed reflection reentry follow-up (反射失敗後重入)

The supplied `diagnostics (8).zip` identifies source `d6f094a` and Run `RUN-9a04f450-32cd-4547-82c8-5a024e72d82f`. At 2026-10-19 00:15:28 UTC, P002 first failed JSON decoding: `Expecting ',' delimiter: line 1 column 919 (char 918)`. At 00:15:30, a second entry collided with the existing P002 directory. The previous exception handler overwrote the original fatal reason with that secondary `FileExistsError`. Seven search rollouts and 33 completed transport requests do not establish final evaluation or release. P001 is a new generated candidate; P002 is a failed attempt, not another Skill.

GEPA 0.1.4's `_propose_texts_batch_safe` catches an adapter exception and retries each task before the next stop callback. A stop-only fatal latch therefore did not enforce the intended no-retry boundary. The adapter now latches the first exception and returns GEPA's native empty update; any reentry returns without touching generation, model calls or artifacts. The next stop check ends search, and search raises the original failure before selection or final evaluation. Existing directories remain protected: there is no overwrite, deletion or `exist_ok` workaround. Transport, JSON, Skill validation and evidence errors all remain fatal.

The reflection instruction now explicitly requires JSON escaping, no Markdown fences and a concise body within the existing output budget. Decoding remains strict: there is no speculative extraction, JSON repair or extra model request. The redacted support ZIP omits raw responses, so it cannot establish whether the user's malformed JSON came from unescaped text, truncation or another content defect. This prompt guidance has not been qualified against the user's GPU model.

Focused proof uses the actual pinned GEPA/nanobot loop with a scripted HTTP server. A valid P001 followed by malformed P002 produces exactly two reflection requests, seven search rollouts, 21 total requests and zero final rollouts. The original JSON error survives in terminal state, the failed audit and the actual exported Skill artifact; no SDK batch fallback, selection, approval or leaked provider slot occurs. The case uses the existing 20-rollout/122-request fixture ceiling (its expected failure ends at seven), ten-second requests and the unchanged workload-derived workflow/cleanup bounds. Direct reentry tests also cover invalid Skill, transport and evidence-write errors. Successful standard and exploration paths separately exercise immediate verification, evaluator and reviewer replay and approval; scripted success is distinct from a new real-model improvement.

The execution graph remains runtime coordinator → worker → native GEPA → nanobot task subprocesses and bounded trusted-test subprocesses; failed reflection ends in worker and does not dispatch later roles. Successful checks continue through reflector, evaluator, reviewer and explicit approval replay. Each trusted-test subprocess retains its five-second cap; exact integration cases use their workload-derived workflow bound plus 30 seconds for terminal collection, with separately counted approval replays. No runtime deadline, release gate, dataset, model budget or historical Run is changed.

The added exact failure case expands the GEPA acceptance manifest from 13 to 14 cases. The manifest-count regressions initially detected the stale expected count; both expectations now include this case, and each expanded case remains within its existing 7,200-second parent cap. Local scoped verification passes 24 distinct cases: four actual SDK workflow cases, twelve exploration/history cases and eight budget/manifest cases. Ruff, source credential-pattern scan and whitespace checks pass. No full M acceptance or Windows/GPU run is claimed.

The same upload also contains a completed **LLM title-normalization** Run `RUN-dbce27d6-70fa-46aa-9c54-c8733bf90404`: one new C1 candidate, final validation 0/2 → 2/2, held-out 1/2 → 2/2, checks passed and release eligible. This is independent evidence of improvement for that task, not proof of GEPA Python-repair improvement or an activated version. The older interrupted GEPA Run `RUN-2a37a595-6638-4351-a276-3f225b8db31a` retains two new proposals but has no final outcome; interruption alone does not identify an OS reboot.

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

[Multi-candidate exploration](gepa-exploration.md) supports sixteen GEPA proposals per Run. Strategy, acceptance policy, seed, duplicate/rejection decisions and coverage accompany the existing instruction/Parent records. The GUI defaults to twelve proposal slots for the shipped bank; saved attempts never imply twelve distinct bodies or twelve approved releases.

## Verification (驗證)

Focused tests cover unchanged/unselected/failed candidates, interrupted response recovery, refused overwrite, read-only behavior, redaction through the actual ZIP consumer, history older than ten Runs, approved-version metadata, pagination, input bounds, origin enforcement and stale replies. Actual pinned GEPA/nanobot SDK workflows with scripted loopback responses check both generation and perfect-score skips; separate real subprocess LLM and rule workflows check failure capture and every unchosen rule probe. Original repair/evaluation/approval/tamper gates and model-call counts remain intact. This validates implementation behavior, not a new Windows/GPU evolution gain or broad M7 acceptance.

Validation for this change: 8 archive/API cases, 13 diagnostic cases, 12 existing read-only history cases, 61 focused frontend cases and five exact subprocess/SDK integration cases passed. Ruff, the staged source credential-pattern scan and diff checks passed.

## Failure/diversity policy follow-up (失敗導向與去重)

New exploration freezes `failure-diversity-v2`. All model attempts remain retained, including pre-evaluation duplicates and stagnation stops. `changed` still means changed relative to the recorded parent. The read-only projection additionally reports per-Run `novelty` and `duplicateOf`, so repeated proposals cannot inflate the different-body count. Saved review metrics and eligibility appear under `outcome`; these are historical persisted results, not fresh verification or automatic approval. Raw model requests, task source and test answers remain excluded from support ZIPs. See [the current exploration policy and workload proof](gepa-exploration.md).
