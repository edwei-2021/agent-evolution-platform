# Live Runtime — v0.4.0 (實際執行與狀態監控)

The local Web interface now reads actual process evidence through polling. This release supplies native tool agents, not LLM agents: it does not call nanobot, GEPA or a model provider. The separate evolution demonstration still uses synthetic fixtures. Version 0.4.0 adds a measured local rule-search workflow under **本機技能實驗**; see [the skill evolution guide](skill-evolution.md). The runtime monitor shows process evidence for either workflow.

Version 0.3.1 fixes the browser `Failed to execute 'fetch' on 'Window': Illegal invocation` error. The default HTTP transport now binds native `fetch` to the browser global object, so polling and workflow start/cancel requests reach the local API. No additional packages are required.

## Update and inspect first (先更新與檢查環境)

Stop the old project server with Ctrl+C. In WSL2:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --check --python python3.11
```

The doctor checks the existing Python/Node environment, standard-library SQLite and Linux file locking, and required frontend/runtime files. This upgrade has no additional third-party packages. If prerequisites are missing, run the installer; otherwise start directly:

```bash
bash scripts/start-gui.sh
```

Open `http://localhost:8765` in Windows. `--port 9000` selects another port for both GUI and API. To inspect the GUI without a supervisor, use `bash scripts/start-gui.sh --static-only`; polling then reports the runtime unavailable.

After updating, use **Ctrl+Shift+R** in the Windows browser to reload frontend modules, then open `http://localhost:8765/#runtime`. Confirm the UI version is **v0.4.0**, the last successful update time is populated and the polling count keeps increasing. Choose **執行專案檢查** to create a workflow; PID/output/history appear once it starts. The WSL terminal should log `GET /api/v1/runtime/capabilities`, repeated `GET /api/v1/runtime` and `POST /api/v1/runtime/runs` when starting work. If `Illegal invocation` remains, verify `git log -1 --oneline`, the displayed UI version, and that the server uses the updated checkout.

## Run and observe (啟動與觀察)

1. Open **執行監控**. A successful connection displays the last successful poll time and polling count.
2. Keep exactly one enabled configuration for each role: coordinator, worker, evaluator, reflector and reviewer. Rename/reassign IDs if needed; role identities are frozen when submitted.
3. Choose **執行專案檢查**. The server queues the fixed workflow and starts real child processes. Current Runtime strings, models, tool names, Skill assignments and graph relationships are metadata and do not alter these commands.
4. Inspect status, PID, observed liveness, task, timestamps, exit code and recent output for every role. The agent list/detail/graph also show the latest run state for matching IDs. Framework-connected count remains zero.
5. Review the event list and artifacts after completion. Jobs that complete between polls remain visible in the history and include actual PIDs/output; no artificial delay is added to make stages appear active.

| Role (角色) | Actual work (實際工作) | Evidence |
| --- | --- | --- |
| Coordinator | Inspect GUI assets and calculate SHA-256 hashes | `manifest.json` |
| Worker | Run all JavaScript regression tests with the detected Linux Node | `javascript-tests.log`, `worker-result.json` |
| Evaluator | Run trusted Python installer/server tests (`setup_test.py`) | `python-tests.log`, `evaluator-result.json` |
| Reflector | Analyze actual test exit codes with fixed rules | `reflection.json` |
| Reviewer | Review results and hash evidence artifacts | `review.json` |

The order is fixed and sequential. Reflection is rule-based reporting, not GEPA evolution. No code repair, model reasoning, Skill mutation or release publication occurs. The native role scripts are process-backed workers rather than installed instances of the frameworks shown in configuration.

A role script can complete successfully while recording failed tests. The final review then sets `checksPassed=false` and the overall workflow fails. Read the test result JSON/logs, not only the stage process exit code. An unexpected script failure skips later stages.

## Polling controls (Polling 控制)

Default polling delay: **2 seconds after the preceding refresh completes**. Select 1, 2, 5 or 10 seconds. Requests do not overlap; each has an 8-second timeout. **立即更新** fetches a fresh snapshot, and **暫停 polling** stops browser updates while the server continues its work. Closing the tab also leaves a running workflow intact while the local server stays running. Browsers may throttle background tabs.

A failed poll preserves the last received evidence but marks it stale. Stale data is not proof that a PID remains alive. Auto polling retries and reacquires the service session after restart. Editing a configuration dialog or focusing a text field temporarily defers screen re-rendering to protect input; polling still reads data. After leaving the field, the next poll updates the view.

Choose **取消執行** to request cancellation. The supervisor terminates its active process group, records cancellation and marks waiting stages cancelled. A per-stage deadline is 120 seconds; child test commands have a 90-second timeout. One workflow runs at a time, and one supervisor can hold the same checkout lock.

## Data on D (D 槽資料位置)

| Item | Location |
| --- | --- |
| SQLite snapshots/history | `/mnt/d/nanobot-gepa-mvp/.local/runtime.sqlite3` |
| Supervisor lock | `/mnt/d/nanobot-gepa-mvp/.local/runtime.lock` |
| Frozen role bindings and artifacts | `/mnt/d/nanobot-gepa-mvp/.local/runs/RUN-<uuid>/` |
| Project temporary files and caches | Existing `.local/tmp/` and `.local/cache/` |

These files are excluded from Git. The monitor lists the ten latest runs; SQLite and run directories retain older records. Browser JSON export backs up registry/demo data, not server execution history. Back up server runtime files after stopping the service for a consistent copy.

Stopping the server cancels its current workflow. After an abrupt restart, unfinished persisted work is marked `interrupted`; previous PID liveness is unconfirmed and no task is automatically resumed. The service is not a durable background queue or system service.

## Local and hosted boundaries (本機與託管介面)

The Python server binds to `127.0.0.1`. API calls are same-origin, mutations require a local session token, and foreign Host/origin requests are rejected. No provider secrets are entered in the browser. This protects local browser mutations; it is not account authentication or a multi-user deployment.

The existing private Site hosts the upgraded static interface, but it does not execute Python or automatically reach your WSL machine. Its live monitor correctly shows the local service unavailable. Use the WSL localhost interface for actual execution. Authenticated remote transport/proxy support is a later deployment step; no firewall or sharing setting is changed in this release.

## Next adapter boundary (後續 Adapter 邊界)

Replace individual fixed role commands with validated nanobot and GEPA adapters after environment/provider configuration is available. Keep live process evidence separate from model/task-quality evidence, persist immutable execution configuration, and preserve the polling contract. Do not label framework connections or evolved Skills as ready based on this native-tool health check.
