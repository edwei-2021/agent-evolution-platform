# Proposed backend contract (not implemented)

This document defines a future integration seam. There is no HTTP adapter or backend in v0.2.0. Do not point the current GUI at nanobot's chat endpoint or a GEPA process and expect evolution orchestration.

## Service resources

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

The v0.2.0 `DemoAdapter` owns synchronous browser-local `saveAgent`, `removeAgent`, `addRelationship` and `removeRelationship` operations. These are not HTTP calls or Runtime commands. An agent record is configuration; `enabled` does not mean running. `connection` is always `disconnected` in demo data. The registry is limited to 30 agents and 120 directed relationships. Skill IDs refer to a fixed local catalog, and the Worker target Skill body follows the active demo release.

A real service must distinguish config revision from live execution telemetry. Connection state requires authenticated adapter evidence and timestamps, never a browser edit. Credentials belong to a server-side secret store; agent responses may carry a credential reference, not the secret. Tools are identifiers until an authorized runner validates an allowlist. GEPA belongs to the optimizer integration rather than the Runtime list. A graph expresses intended handoff relationships, while real task traces record actual handoffs and failures.

Legacy workspace backups (schemaVersion 1) gain the starter registry when imported. Version 2 exports include the registry, experiments and releases together. The browser storage key remains unchanged for migration; demo and future real workspaces must remain separate.
