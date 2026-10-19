# Runtime Diagnostic Logs (執行期診斷紀錄)

The GUI automatically records categorized local metadata after startup. A download combines these logs with recent persisted status and source identity, so troubleshooting can use one archive rather than screenshots and repeated model runs.

## Start and collect (啟動與收集)

After updating the checkout, stop the existing GUI and start it normally:

```bash
bash scripts/start-gui.sh
```

The terminal prints the diagnostic directory. Open **Module Log → 下載診斷包** to download `diagnostics.zip`. This operation reads local evidence only; it does not import/probe an SDK, call Ollama, retry a request, or start an experiment.

Command-line alternative:

```bash
.venv/bin/python scripts/export_diagnostics.py
```

The command prints `DIAGNOSTIC_SUPPORT` followed by the saved ZIP path. An explicit `--output /path/to/diagnostics.zip` is also supported. New instrumentation applies to future operations; old raw role files and the existing SQLite journal remain available through their existing views.

## Separate files (分類檔案)

Files live under `.local/diagnostics/` in the existing checkout:

| File | Recorded metadata |
| --- | --- |
| `startup.jsonl` | Process/session identity, interpreter/version, platform, workspace/temp paths, Git revision at startup, binding/readiness, shutdown and uncaught startup errors |
| `http.jsonl` | Local GUI method/path/status, API operation spans and unhandled request errors; query strings and request bodies omitted |
| `sdk.jsonl` | Package/interpreter, required/observed version, metadata/import stage, elapsed/deadline, exit/error classification and bounded stderr tail |
| `ollama.jsonl` | Explicit provider requests and setting events, endpoint/model, proxy bypass and transport metadata |
| `warmup.jsonl` | Frozen endpoint/revision/limits, worker PID, periodic local wait, connection/response phases, bounded worker output, exit code, cancel source and terminal result |
| `model-calls.jsonl` | Run/request/call correlation, endpoint/model, connection, HTTP status, first received data, completion/failure and elapsed time |
| `workflows.jsonl` | Workflow/role/tool spans and output-observation metadata; full role stdout remains in the original run files |
| `status.jsonl` | Latest persisted Run ID, original timestamps, role PIDs/status/errors, frozen code hashes/limits, provider busy and warmup identity/status; emitted only on changes |
| `errors.jsonl` | Error-level events mirrored from the other categories, with source category and structured exception metadata |

Records include UTC timestamps, PID, thread, startup session (when launched by the GUI), correlation ID and structured details. Transport events also have a unique request ID. UTC timestamps retain their offset; the existing log UI displays Taiwan time.

Each category rotates at **2 MiB**, retaining two older files (`.jsonl.1`, `.jsonl.2`). Per-category process locks protect rotation and complete JSON-line writes. Locks cover only append/rotation, with no model work, network, SQLite transaction or explicit fsync inside the lock. Diagnostic storage is supplementary; a write failure does not change model scoring or successful request results.

## Interpret transport stages (連線階段判讀)

| Last observed stage | Interpretation |
| --- | --- |
| `request.started` without `connect.started` | Request preparation/dispatch has not reached connection setup |
| `connect.started` without `connect.completed` | Failure during address resolution or connection establishment; inspect exception type/errno |
| `connect.completed` then `response.waiting` | Connection established; HTTP response headers have not arrived |
| `response.headers` then `response.reading` | Status received; waiting for response data/completion |
| `response.first_data` | Response data arrived; later failure belongs to response decoding/stream/completion processing |
| `request.completed` | Transport operation completed; inspect the separate operation/workflow result |

The current provider uses HTTP to a saved IPv4 endpoint; detailed connection hooks cover that path. Errors retain the original phase, exception/reason type, errno, HTTP status where available, elapsed time and bounded stack-frame locations. An OS connection timeout may occur before an application's larger configured deadline; increasing the deadline alone does not identify or repair it.

Warmup remains an explicit empty-prompt preload request. `PRELOAD_PASS` records that operation's completion, without claiming that a real generation was verified or that the model will remain resident indefinitely. A canceled local preload may still be processing on the remote Ollama server. Cancel events distinguish operator requests from service shutdown. No retries or additional model probes were introduced.

## Archive contents and boundaries (匯出內容與範圍)

The ZIP contains categorized metadata logs, `status.json`, `source.json`, an export manifest and explicit `skills/RUN-….json` artifacts. See [Skill generation history](skill-generation-history.md) for instruction text, lineage, generation conditions, older Runs and per-Run exports. Status collection reads the runtime database in read-only mode, plus saved warmup/settings. Startup revision describes the launched service; source hashes/revision in `source.json` describe files currently on disk. Old Run timestamps and frozen hashes remain historical evidence even after code updates.

Bounded repair runs now include a projected `repairTrace` in `status.json`: visible passed/total counts, source hashes, request finish reasons, summary mode and native SDK stop reason. The projection reads existing bounded files only and also works for older repair traces. `limits.outputLimit` preserves the numeric output budget without exposing credentials. Source identity now includes the repair runner and SDK bridge. See [repair completion](repair-completion-followup.md).

GEPA Runs also include `gepaRepairTrace` for their last recorded active rollout, with its task/rollout IDs and the same body-free repair projection. Saved rejected replies retain actual finish reason, recognized tool names/count, content/response flags, reported completion count and output limit. This can recover details for an already failed Run without rerunning the model. The previous generic error logger cleared response metadata on failure; historical null finish reasons in those log lines must not be treated as evidence that the server omitted a finish reason. The new projection reads original local artifacts, not the old lossy log fields.

Exports exclude raw model request/response artifacts, task source and full SDK role output. The explicitly requested Skill-artifact section retains bounded redacted instruction text and diffs separately from body-free logs. Credential fields and prompt/content fields are redacted; known HTTP error bodies are omitted. Logs can contain endpoint/model identifiers, local paths and execution IDs needed for diagnosis. Symlink files are excluded, individual reads are bounded, and total log input is capped at 32 MiB. Concurrent rotation/partial lines and omitted files are reported or preserved as bounded partial records.

The archive does not contain Windows Ollama's own server log or GPU telemetry. Connection metadata can identify the failing boundary; determining firewall, listener, routing or remote-server causes may still require evidence from the affected machine. This feature does not claim to repair a user's Windows connection or qualify a new target-model run.

## Focused verification (針對性驗證)

Local tests cover actual service startup/shutdown and bind failure, cross-process JSONL writes/rotation, redaction and body exclusion, connection refusal, injected OS connection timeout, real header/body stalls, failed preload child cleanup/retained metadata and stderr/exit-code capture. Bundle tests verify read-only export, origin enforcement, symlink exclusion, absence of SDK/model dispatch and state-change filtering.

Existing warmup lifecycle/deadline/cancellation, provider, journal, transport, SDK discovery and trace-reuse regressions remain checked. Actual SDK repair and the GEPA iteration cap are checked in an offline verification environment using the SDK's built-in conservative tokenizer fallback; the normal tokenizer download could not be qualified in this environment. No full M7 rerun or real GPU/Windows acceptance is claimed.

## Saved evolution outcome projection (已保存演化結果)

Skill artifacts now include bounded `outcome` fields from the persisted review result: final baseline/selected validation and held-out passed/total counts, checks/eligibility and request/rollout/proposal counts where present. Export never recomputes scores or imports an SDK. Missing results stay null; partial measurements do not become approval. Candidate novelty and pre-evaluation duplicate decisions remain separate from parent diffs and formal versions. This closes the previous support-package gap where a completed Run was visible but its final score comparison was unavailable.
