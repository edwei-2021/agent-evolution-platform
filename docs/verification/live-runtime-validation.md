# Live Runtime verification — 2026-10-11

## v0.3.1 browser fetch hotfix (瀏覽器連線修正)

The user's screenshots show WSL2 Ubuntu 24.04.5 / Python 3.11.9 / Linux Node 22.23.3 and a READY doctor report. The local server serves GUI modules successfully, but the browser reports `Failed to execute 'fetch' on 'Window': Illegal invocation` and the terminal receives no runtime API requests. The default transport stored native `fetch` as a client method, changing its receiver to the RuntimeClient instance.

Native `fetch` is now bound to `globalThis`; injected test transports are retained. A receiver-sensitive default-transport regression test reproduced the exact error before the fix, and passes after it. It covers repeated polling plus token-bearing start/cancel requests. All **36 JavaScript + 25 Python tests** pass, including actual native-role subprocess checks. Module/shell syntax checks and `git diff --check` also pass.

A separate HTTP integration check uses the default RuntimeClient with a receiver-sensitive, relative-URL browser-fetch shim against an actual loopback server. It successfully obtains capabilities, submits work and completes 42 refreshes. All five roles report real PIDs and zero exit codes, and final `checksPassed=true`. Temporary smoke runtime data is cleaned up. This is HTTP/controller/process verification, not a real Chrome DOM test.

The development environment was checked again: Python 3.12.14, Linux Node 24.19.0 and ready `.venv`; it remains a non-WSL container. No packages were installed. The user's Chrome/Windows/WSL host cannot be operated from this session; browser visual QA remains unavailable. Update/restart/hard-refresh and API-log verification steps are documented in `docs/live-runtime.md`.

## Original v0.3.0 verification

Release: v0.3.0. Target: WSL2 Ubuntu 24.04, Python 3.11+, project under `/mnt/d/nanobot-gepa-mvp`.

## Environment inspected first (先檢查環境)

The read-only doctor was run before development and again after the runtime upgrade. Available build environment: Ubuntu 24.04.3 container, ordinary Linux 6.18.44 kernel, Python 3.12.14, Linux Node 24.19.0 and a usable project `.venv`. It correctly reports NOT READY for the WSL target because this environment is not WSL2. Image-provided command tools are not represented as installed APT package records. No system package changes were made. Python SQLite/file-locking support is available; the upgrade requires no third-party packages.

nanobot, GEPA, FastAPI and uvicorn were not installed. No OpenAI, Anthropic or OpenRouter model API key was configured in the build environment; only presence booleans were inspected, never secret values. This release implements a standard-library native-tool workflow, not model or GEPA execution.

## Tests (測試)

- 35 JavaScript tests: prior registry/demo/controller coverage plus seven live transport/polling tests for capabilities reuse, no-store requests, non-overlapping polls, periodic updates/pause, token-bearing mutations, stale evidence, restart handling, invalid response rejection and text escaping.
- 25 Python tests: prior 15 installer/HTTP tests plus ten actual process/API tests for PID/output/exit evidence, persistence/idempotency, process-group cancellation, deadline termination, supervisor locking, restart interruption, role validation, real project-health tasks and same-origin/token/Host/artifact restrictions.
- The fixed native pipeline is executed with real child processes in tests. Worker runs actual JavaScript tests; Evaluator runs actual trusted Python installer tests. The final `checksPassed` is true, reflection leaves Skills unchanged and review records `published=false`.
- Bash entry scripts pass syntax checks. All frontend modules pass syntax/import-target checks and HTML asset references resolve. `git diff --check` passes.

## Real launcher/API smoke check (實際啟動驗證)

`start-gui.sh` is launched from outside the checkout with a dynamically selected port. The GUI and new module assets return HTTP 200. The smoke check obtains capabilities, submits a real workflow with the same-origin mutation token, repeatedly fetches snapshots and observes both running and completed states. All five role processes report actual PIDs and zero script exit codes. The final review artifact reports passing checks and no publication. Ctrl+C shuts down cleanly. Project working directory and reported URL are verified.

SQLite and run artifacts created by this smoke check remain in ignored `.local/` paths. They are validation evidence from the development container, not the user's WSL host or production model evidence.

## Verification limits (驗證範圍)

Browser visual and full DOM interaction QA are unavailable because the managed preview requires a Browser control skill absent from this session. No screenshot/mobile rendering checks are claimed. The user's WSL host, Python 3.11 executable, Windows localhost forwarding and D / DrvFS behavior were not directly tested. Re-run the doctor on the user host after pulling.

No real nanobot/GEPA adapter, LLM reasoning, Skill mutation, workflow evolution or remote WSL connection was executed. Hosted Sites serves static assets and cannot run the local Python supervisor; live monitoring requires the local same-origin Web interface.
