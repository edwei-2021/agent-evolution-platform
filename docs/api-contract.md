# Runtime API and proposed evolution service contract

v0.4.1 adds explicit Ollama provider endpoints; v0.4.0 implements local runtime and measured declarative-skill endpoints. Simulation experiments/releases and registry editing remain browser-local; model-agent/GEPA endpoints below remain future integration seams. Do not point the current GUI at nanobot's chat endpoint or a GEPA process and expect evolution orchestration.

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

Provider status is separate from agent-framework connectivity. `modelConnected` remains false in runtime capabilities because the Skill/agent workflow does not execute models yet; `workerIntegrated` is false in the provider snapshot. Historical `METADATA_ONLY_PASS` does not become a live connection badge. The saved configuration is authoritative; imported browser registry/demo backups do not overwrite it.
