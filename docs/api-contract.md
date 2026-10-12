# Runtime API and proposed evolution service contract

v0.5.0 implements actual Ollama model Skill workflows plus the existing provider, runtime and declarative-skill endpoints. Simulation experiments/releases and registry editing remain browser-local; external nanobot/GEPA adapter contracts remain future integration seams. Do not point the current GUI at nanobot's chat endpoint or a GEPA process and expect evolution orchestration.

## Implemented local runtime API (已實作的本機執行 API)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/runtime/capabilities | Service identity, local mutation token and detected tool availability |
| GET | /api/v1/runtime | Server timestamp, latest full run snapshot and ten recent summaries |
| POST | /api/v1/runtime/runs | Submit the fixed project-health task with role bindings and an idempotency request ID |
| GET | /api/v1/runtime/runs/{id} | Read a persisted run snapshot |
| POST | /api/v1/runtime/runs/{id}/cancel | Request termination of the active process group |
| GET | /api/v1/runtime/runs/{id}/artifacts/{name} | Inspect an allowlisted JSON/log artifact, bounded to 200,000 characters |

Requests are same-origin on the loopback server. Mutations require `X-Lab-Token` from capabilities, JSON content type and a body at most 128 KB. Unknown endpoints/artifacts return 404, invalid input 400, invalid token/origin/Host 403 and concurrent workflows 409. There is no CORS endpoint setting or browser credential entry.

Submission body: `{registry, requestId}`. The server validates and projects enabled agent identities to exactly one of each fixed role. It never executes browser-supplied commands, Runtime strings, tool identifiers, model settings, Skill bodies or custom graph edges. Idempotency preserves the prior run ID for repeated request IDs. Run evidence is authoritative server data and is never imported into the demo registry as a connection claim.

Snapshot fields include `serviceId`, `serverTime`, `latestRun`, and `runs`. Per-agent telemetry includes identity/role, adapter, status, task, PID, observed process liveness, start/end/update times, exit code, error and an 8 KB output tail. PID is execution evidence, not an LLM session ID. A completed role means its script exited successfully; the trusted test exit codes and final review determine `checksPassed`. A workflow can end failed when tests fail even if every stage process exited normally. Persisted running work becomes interrupted after supervisor restart.

## Implemented measured Skill API (本機實測技能 API)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/skills | Active policy/version, revision, immutable versions, actions and recent Skill runs |
| POST | /api/v1/skills/runs | Submit `{registry, requestId, maxCandidates, expectedRevision}`; candidate limit 1–4 |
| POST | /api/v1/skills/runs/{id}/approve | Trusted evidence recomputation, version creation and local activation; body `{expectedRevision}` |
| POST | /api/v1/skills/versions/{id}/activate | Activate/roll back an existing immutable version; body `{expectedRevision}` |
| POST | /api/v1/skills/execute | Trial using the active policy; body `{text, expectedRevision}`, text at most 500 characters |

These routes use the same Host/origin/session-token/body limits as runtime routes. State conflicts return 409; invalid policy/evidence/input returns 400. Browser-supplied scores are ignored. Only a completed, improving, independently verified run with the current active baseline can be approved. A version remains immutable; activation changes a revision-checked pointer and records an action. Existing work retains its frozen baseline. Default maximum: 100 stored versions.

`GET /api/v1/runtime` includes a `skills` workspace without changing the existing schemaVersion 1 process contract. Its Skill `latestRun` contains frozen `skillConfig`, atomically read `skillProgress` and terminal `skillResult`. `GET /api/v1/runtime/runs/{id}` also supplies these fields for history selection. Cancellation uses the existing runtime cancel route. Artifact access now includes allowlisted `.md` files alongside `.json`/`.log`.

Project-health and Skill runs share the active-workflow slot. Submission IDs bind immutable task/role/options projections; reuse with different input returns 409. Optimizer engine is `local-rule-search-v1`, not GEPA. Capabilities exposes `skillEngine`; `frameworkConnected` and `modelConnected` remain false. See `docs/skill-evolution.md` for exact evaluation counts and evidence scope.

## Proposed evolution service resources

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/agents | Server-owned agent configurations and separately measured connection state |
| POST | /api/v1/agents | Create a validated agent configuration |
| PATCH | /api/v1/agents/{id} | Update configuration with a revision check |
| DELETE | /api/v1/agents/{id} | Remove configuration and its relationships under a server policy |
| GET | /api/v1/relationships | Directed source/recipient relationships and deliverables |
| POST | /api/v1/relationships | Validate endpoints and create a directed relationship |
| DELETE | /api/v1/relationships/{id} | Remove a relationship |
| GET | /api/v1/capabilities | Runtime/optimizer availability and real-mode readiness |
| GET | /api/v1/experiments | Workspace-scoped experiment list |
| POST | /api/v1/experiments | Validate configuration and create queued experiment |
| GET | /api/v1/experiments/{id} | Immutable config, current state and summary |
| POST | /api/v1/experiments/{id}/actions | start, pause, resume, cancel with state revision |
| GET | /api/v1/experiments/{id}/events | SSE stream with monotonically increasing event IDs |
| GET | /api/v1/experiments/{id}/artifacts | Skill bodies/diff, evaluator evidence, traces and hashes |
| POST | /api/v1/releases | Review and publish selected real candidate |
| POST | /api/v1/releases/{id}/activate | Change active skill pointer for future tasks |

Authentication is server-owned; use an authenticated session and CSRF protection for cookie-based mutations. Job submission and release operations require authorization. Apply idempotency keys to mutations, revision checks to state changes, and bounded request sizes. A pause means no new evaluations are scheduled; an in-flight evaluation either completes or is cancelled according to an explicit worker policy.

## Experiment snapshot

Required fields: `schema_version`, `id`, `mode` (`real` / `demo`), `revision`, `name`, `status`, `config`, `progress`, `metrics`, `provenance` and `artifact_refs`. Unmeasured metrics are null, never inferred from demo fixtures. For real mode, provenance must identify skill/data/split/evaluator/runtime revisions and model/tool/memory configuration. A completed job is not automatically an approved release.

Every evaluation record includes task ID, split, skill version/hash, objective score, termination reason, timing, token usage/cost, isolation/session identifier and trace reference. Metrics show numerators and denominators with repeat policy. Do not expose held-out examples to the optimizer or a reusable training trace cache.

## Adapter migration

Replace `DemoAdapter` with an asynchronous HTTP implementation and update event handlers to await requests. Move ticking to the worker; subscribe to SSE for authoritative state, reconnect with Last-Event-ID and poll if streaming is unavailable. Validate response data and display connection errors without silently falling back to demo. Separate demo and real workspace stores. Real release gating must run server-side; the browser gate is presentation only.

## Agent registry boundary (代理人設定邊界)

The v0.3.0 `DemoAdapter` owns synchronous browser-local `saveAgent`, `removeAgent`, `addRelationship` and `removeRelationship` operations. These are not HTTP calls or Runtime commands. An agent record is configuration; `enabled` does not mean running. `connection` is always `disconnected` in demo data. The registry is limited to 30 agents and 120 directed relationships. Skill IDs refer to a fixed local catalog, and the Worker target Skill body follows the active demo release.

A real service must distinguish config revision from live execution telemetry. Connection state requires authenticated adapter evidence and timestamps, never a browser edit. Credentials belong to a server-side secret store; agent responses may carry a credential reference, not the secret. Tools are identifiers until an authorized runner validates an allowlist. GEPA belongs to the optimizer integration rather than the Runtime list. A graph expresses intended handoff relationships, while real task traces record actual handoffs and failures.

Legacy workspace backups (schemaVersion 1) gain the starter registry when imported. Version 2 exports include the registry, experiments and releases together. The browser storage key remains unchanged for migration; demo and future real workspaces must remain separate.

## Explicit Ollama provider (Ollama 模型服務介面)

All routes use the existing loopback Host/Origin policy. POST requires JSON and `X-Lab-Token`; the token comes from `/api/v1/runtime/capabilities`. Settings, metadata and chat bodies require `expectedRevision`. Neither GET nor settings POST makes an Ollama network request.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/v1/llm/ollama` | Saved config/revision, resolved endpoint, historical user evidence and latest request record |
| POST | `/api/v1/llm/ollama/settings` | Save `{config, expectedRevision}` atomically; increment revision |
| POST | `/api/v1/llm/ollama/metadata` | Explicit native version/tags and OpenAI model-list requests |
| POST | `/api/v1/llm/ollama/chat` | One chat completion using `{prompt, expectedRevision}` and saved config |

Config fields: `host` (empty for WSL NAT discovery or an IPv4 override), `port` (11435), `model` (empty until selected), `metadataTimeout` (10), `inferenceTimeout` (600), `maxTokens` (256). Numeric settings are bounded integers. Invalid input returns 400; an outdated revision or simultaneous provider operation returns 409 without dispatch. A dispatched provider failure returns a persisted operation record with `status: FAIL` and `error`; this is not a successful inference. Records pin config/revision/endpoint and include timestamps, elapsed time, report path and actual output/usage when present. No automatic retry occurs.

Provider status is separate from agent-framework connectivity. `modelConnected` remains the legacy external-framework flag. Version 0.5.0 exposes `llmWorkerAvailable` and sets provider `workerIntegrated` to true for the actual model Skill workflow; neither is a live reachability probe. Historical `METADATA_ONLY_PASS` does not become a live connection badge. The saved configuration is authoritative; imported browser registry/demo backups do not overwrite it.

## Actual LLM Skill workflow (v0.5.0)

`/api/v1/runtime` additionally returns `llm`, a separate prompt workspace with revision, immutable `LSV-...` versions, active version, latest run and recent runs. A model run has `task: llm-evolution`, `llmConfig`, live `llmProgress` and verified `llmResult`. It reuses the process-status envelope and generic cancellation/artifact routes.

| Method | Path | Body / result |
| --- | --- | --- |
| GET | `/api/v1/llm/skills` | Prompt workspace and current progress, without model requests |
| POST | `/api/v1/llm/skills/runs` | `{registry, requestId, profile, maxSeconds, callTimeoutSeconds?, expectedRevision, providerRevision}`; returns 202 |
| POST | `/api/v1/llm/skills/runs/{runId}/approve` | `{expectedRevision}`; recompute evidence and create/activate an immutable prompt version |
| POST | `/api/v1/llm/skills/versions/{versionId}/activate` | `{expectedRevision}`; rollback/reactivate without deleting evidence |

`profile` is `smoke` or `full`; `maxSeconds` is an integer 60–7200 (GUI default 900). Provider revision binds saved settings. The server resolves/pins the endpoint without a connectivity test; an exact model ID must already be saved. The call budget is fixed at 15/101, including reflection. Strict validation improvement and no held-out regression gate release. HTTP failure/timeout/invalid candidate fails the workflow; task-format errors are scored as failed tasks. There is no automatic model retry or fallback to rule execution.

Model and rule runs share the workflow slot. Model runs additionally reserve the server's provider operation slot. Request IDs bind immutable submissions; a replay cannot change profile, budgets or role bindings. Mutations use the existing Host/Origin/CSRF policy; stale revisions return 409. Provider settings may change during a run but cannot alter its frozen calls. `modelConnected` is the legacy external-framework flag, not a reachability probe; capabilities adds `llmWorkerAvailable: true` and `llmSkillEngine`. Provider snapshots now report `workerIntegrated: true`; no claim of installed nanobot/GEPA is made.

Artifact previews additionally expose `truncated` and `totalChars` when content exceeds 200,000 characters. Complete evidence remains under `.local/runs/`.


## Observable execution progress (v0.5.2／執行進度)

All runtime run snapshots add `executionProgress`: `elapsedSeconds`, `completedStages`, `totalStages`, `stage` and `heartbeatAt`. This is observed subprocess telemetry; the stage denominator is the five configured roles, not model-inference completion percentage. Terminal snapshots freeze elapsed time at `endedAt`.

LLM submission accepts optional `callTimeoutSeconds` (integer 10–3600, default 120); omission preserves compatibility with earlier clients. Frozen `llmConfig` adds `transport: "openai-sse-v1"` and an effective `callTimeoutSeconds` capped by the saved provider limit. Each call is further capped by remaining workflow time. Unknown fields and invalid/bool values are rejected before dispatch.

`llmProgress.calls` remains dispatched requests. Added `completedCalls` and `failedCalls` count terminal transport calls; a formatted but incorrect task answer still completes its transport call and fails task scoring. `lastCall` adds `startedAt`, `deadlineEpoch`, `timeoutSeconds`, `responseStartedAt`, `firstChunkAt`, `lastChunkAt`, `chunks`, `outputChars`, `reasoningChars`, `finishedAt`, `elapsedMs` and failure `error` as applicable. Call timestamps use epoch seconds; role timestamps remain ISO strings. Character counts are not token usage and do not estimate model completion percentage. `lastCall` excludes request/response text and full stream events from polling snapshots. SSE events and normalized response are retained in local evidence for review. Cancelled or killed calls are finalized only after the worker stops. No further requests are submitted after cancellation, timeout or transport failure.


## Explicit native preload (v0.5.3／模型暖機)

`POST /api/v1/llm/ollama/warmup` accepts `{expectedRevision, keepAliveMinutes?}` (default 15, integer 1–60) and returns 202 with a separately identified `WARM-...` job. Unknown fields, missing model or stale revision are rejected before dispatch. It freezes saved provider settings/endpoint and uses `inferenceTimeout` as its independent absolute limit. `POST /api/v1/llm/ollama/warmup/{id}/cancel` stops the locally supervised job; it does not unload the remote model. Both use the existing local Host/Origin/CSRF boundary.

`GET /api/v1/llm/ollama` adds `warmup`; `/api/v1/runtime` adds `provider: {revision, config, busy, warmup}` so normal polling can observe it. States: `RUNNING`, `PRELOAD_PASS`, `FAIL`, `CANCELLED`, `INTERRUPTED`. Job fields include ID, pinned revision/config/endpoint, keep-alive preference, timeout, timestamps, elapsed seconds, optional native load/total duration milliseconds and failure reason. `PRELOAD_PASS` records completion of one native preload, not live residency or inference accuracy. It is separate from manual `latest` request reports and all experiment budgets. No GET triggers an Ollama request.

## Local journal API (v0.5.3／模組紀錄)

- `GET /api/v1/debug/logs?module=&level=&runId=&q=&before=&limit=`: exact module/level/run filters and substring search; default limit 100, maximum 500, query length 200 and run ID length 80. Duplicate/unknown parameters are rejected. Records are newest first; `nextBefore` is an exclusive decreasing-ID cursor. Response includes matched count, retained count, retention cap, oldest/newest IDs, supported filters and server timestamp. No request is dispatched to Windows.
- `POST /api/v1/debug/logs`: `{level,message,page}` reports a browser-originated `gui` record. Maximum message 2,048 characters, page 80, validated level, local session token required. The service caps browser reports at 60 per minute. Logging failures are not recursively reported.
- `GET /api/v1/debug/runs/{runId}/{role}`: read a fixed role log from a stored run. Returns `{runId,role,content,truncated,totalBytes}`; preview is the last 200,000 bytes, including active/pre-upgrade runs. Invalid/external paths are rejected. Reading does not rerun roles or models.

Journal records contain `{id,at,module,level,runId,message,details}`. IDs are stable and monotonically increasing; retention removes old rows rather than resetting IDs. Original UTC timestamps remain in JSONL export. Common secret patterns and structured prompt/content/reasoning fields are redacted. Routine successful polling and journal reads do not create repeated API records. Journal storage is bounded and independent of evaluation evidence.


## Bounded nanobot Python repair (v0.6.0／Python 修復)

`GET /api/v1/repair` and `/api/v1/runtime.repair` expose SDK availability, latest `nanobot-repair` run and the last ten repair runs. SDK inspection is local and does not dispatch model requests. Capabilities additionally reports `nanobotInstalled`, `nanobotSdkVersion` and `pythonRepairAvailable` for the optional pinned environment; these describe SDK availability, not a gateway/network heartbeat.

`POST /api/v1/repair/runs` accepts exactly `{registry,requestId,maxSeconds,callTimeoutSeconds,callBudget,providerRevision}`. Whole time: 60–7200 seconds; call time: 10–3600 seconds; model calls: 2–12; all are integers, with frozen provider revision. Unknown fields are rejected. The server owns the fixed Skill, task, tools, evaluator and SDK selection. Missing/wrong SDK or stale provider revisions fail before model dispatch. Existing localhost Host/Origin/CSRF, immutable submission IDs and shared workflow/provider slots apply. Generic runtime cancellation and history routes are reused.

A repair run adds `repairConfig`, `repairProgress` and independently verified `repairResult`. Progress includes phase, dispatched/completed/failed calls, tool count and last request timing/chunk/text/reasoning/tool-argument character counts. The result distinguishes trusted workflow verification from `repairPassed`; a completed workflow may record an unsuccessful repair. Baseline/candidate visible/hidden counts have fixed denominators of six, with candidate/patch/evidence hashes and SDK version. No approval/activation route exists for this task result.

The artifact allowlist now also permits fixed `.py` and `.patch` filenames belonging to the selected run, subject to the same path/preview checks. API previews are read-only text; complete source/patch bytes remain in local files. Frontend evidence loading reads only baseline, frozen candidate, bounded tool trace and patch and marks truncated previews. `nanobot` is an additional module journal filter. No GET reruns SDK or model evaluation.
