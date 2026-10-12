# Model Preload and Module Logs (模型暖機與模組 Log)

Version **0.5.3** separates cold model initialization from measured Skill calls and adds a persistent local debug journal. No new dependencies or Windows configuration changes are required.

## Preload before a cold experiment (冷啟動前暖機)

The user observed a 240-second first-call failure, then a complete 15-call Smoke run in under 10 seconds after asking the same `qwen3-coder:30b` model a question in Ollama Chat. This strongly suggests that initialization or queue/context preparation dominated the first attempt. VRAM occupancy alone cannot confirm that a model is ready, or distinguish loading, queueing and computation. This release provides a separate explicit preload without claiming to have measured the Windows GPU.

1. Save the exact model ID in **Integrations**. Existing port 11435 and gateway/proxy settings are retained.
2. In **LLM Skills** or **Integrations**, click **Preload model** (預先載入模型).
3. Observe elapsed time and the saved **Inference timeout** limit. This limit is independent of the experiment's single-call and whole-workflow budgets; increase the saved limit if legitimate cold initialization takes longer.
4. After a successful preload record, immediately start Smoke. Preload uses none of its 15-call budget.

Preload sends exactly one native `POST /api/generate` with `{model, prompt: "", stream: false, keep_alive: "15m"}`. It does not pull a model, change server environment variables, run metadata probes, or generate a test answer. A supervised subprocess performs the request; the API returns asynchronously while ordinary polling reports progress. The saved provider settings/revision and resolved endpoint are frozen. The parent enforces an absolute limit, even if the remote connection remains open. A failed, cancelled or interrupted preload cannot be shown as successful. Native `load_duration`/`total_duration`, when provided, are converted from nanoseconds to milliseconds and kept distinct from local wall time.

The shared provider slot prevents overlapping local preloads, manual chat/metadata and model experiments. **Cancel preload** stops the local subprocess and releases that slot without sending an unload request or an automatic retry. Ollama may continue an already dispatched load. A lost submission response also does not trigger a client retry: refresh state to see whether the job started. Restart marks an old pending preload as interrupted/unconfirmed.

A successful record describes that completed request, not current model residency or inference correctness. Ollama can later evict/unload the model, and subsequent API calls may apply their own keep-alive settings. The displayed 15 minutes is the preload request's retention preference, not a guarantee of GPU residency.

## Debug journal (集中除錯紀錄)

Open `http://localhost:8765/#logs` or click **Module Log** in the sidebar. New records persist across browser and service restarts in `.local/debug.sqlite3` using SQLite WAL and bounded retention. They are separate from run evidence, role log files and provider reports.

| Module | Recorded activity |
| --- | --- |
| `api` | Mutating API results and API failures (journal endpoints are excluded); route/status/error, without request bodies, headers or query strings |
| `gui` | Best-effort browser errors, unhandled rejections and polling errors while a local session is available; labeled as browser-originated |
| `runtime` | Service lifecycle, workflow transitions and cancellation |
| `ollama` | Saved provider revisions, explicit metadata/chat outcomes, preload start/result/error/timings |
| `llm` | Model call start/completion/failure, effective timeout, elapsed time, response character/chunk counts, model version approval/activation |
| `skills` | Rule experiment configuration and version actions |
| Role modules | Coordinator, Worker, Reflector, Evaluator and Reviewer transitions and captured subprocess output |

Timestamps are stored in UTC and displayed in **Asia/Taipei**. Role stdout timestamps represent capture time, not an invented timestamp from the child. Model calls carry their run ID, and preload uses a separate `WARM-...` correlation ID. Click an ID to filter related records; API-only errors before run creation may have no run ID.

Filter by module, level, run/preload ID and substring query. The default is the latest 100 records; older pages use stable decreasing IDs. Looking at older pages pauses automatic updates. The page holds at most 1,000 records; use filters to narrow large sessions. **Export current JSONL** downloads exactly the currently loaded records and their structured details, using original UTC timestamps. It does not export the entire database or full model prompts/responses.

The journal retains the newest **10,000 records**. Messages are capped at 2,048 characters and structured details at approximately 4 KB. Common credential fields/patterns are redacted, and prompt/content/reasoning fields are omitted from structured journal details. Full experiment evidence remains in `.local/runs/` and is not copied into ordinary journal records. Journal write failures do not change model scoring or dispatch outcomes; the log API reports storage read failures. High-volume run files remain available separately.

## Existing raw logs (升級前的原始紀錄)

New journal capture starts with this release; it does not fabricate past events. At the bottom of the page, select a recent run and a role to read its existing `.log` file, including pre-upgrade runs and active role files. This is a read-only operation. Only fixed role filenames belonging to stored run IDs are allowed, with resolved-path checks; at most the last 200,000 bytes are previewed. The original file stays in `.local/runs/RUN-.../`.

Windows Ollama's own `server.log`, GPU-Z telemetry and external framework logs are not automatically collected. This page covers implemented local modules; nanobot/GEPA integrations remain future work. The private static Site exposes the frontend, while reading the actual journal requires the WSL localhost API.

## Upgrade (更新)

Stop the GUI with Ctrl+C, then run:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/start-gui.sh
```

Refresh the browser with Ctrl+Shift+R and confirm **v0.5.3**. Existing `.local/` settings, versions, evidence and Windows port 11435 remain intact. No repeated Windows/Ollama connection diagnostics are needed. Back up `.local/` with the GUI stopped if retaining older history is important.

References: [Ollama preload/keep-alive FAQ](https://docs.ollama.com/faq) and [native generate API/timing fields](https://docs.ollama.com/api/generate).
