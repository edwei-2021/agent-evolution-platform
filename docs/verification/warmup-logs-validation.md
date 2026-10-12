# Warmup and Module Log Validation (暖機與模組 Log 驗證)

Release: **v0.5.3**. Linux, Python 3.12.14, Node 24.19.0. No new dependencies. Full regression: **76 JavaScript + 79 Python = 155 passing tests**.

## Observed problem (使用者觀察)

A cold `qwen3-coder:30b` request failed after 240 seconds while GPU-Z showed occupied VRAM. After a Chat question preloaded the same model, Smoke completed 15 calls in under 10 seconds. This is user-reported evidence pointing to cold initialization/queue/context work, not a development measurement of the Windows GPU. The new explicit native preload lets users prepare the model without consuming experiment call budgets or confusing a cold-load wait with measured task execution.

## Implemented behavior (實作)

- Explicit async native preload with empty prompt, a requested 15-minute keep-alive and the saved provider timeout. A supervised local subprocess enforces an absolute deadline. Browser polling shows elapsed time and returned native load duration; a completed preload is historical evidence, not a permanent residency badge.
- Shared provider exclusion across preload, metadata/chat and LLM workflows. Cancellation stops the local job without unload/retry requests. Startup recovers old running preload records as interrupted/unconfirmed.
- Persistent SQLite WAL journal, newest 10,000 records, structured module/level/correlation data, bounded messages/details and common secret redaction. Journal write failures do not change model scoring or dispatch.
- Log page with stable cursor pagination, search, exact module/level/run filtering, stale-state handling, current JSONL export, Asia/Taipei display and read-only existing role logs. Browser reports use the local session boundary and a 60/minute cap. Successful polling and log reads do not generate repetitive API records.

## Verification (驗證)

| Test | Result |
| --- | --- |
| Preload protocol | Actual loopback HTTP receives one `/api/generate` request with the saved exact ID, empty prompt, `stream:false`, `keep_alive:"15m"`; no metadata or generation prompt requests occur. |
| Native timings | Mock native nanosecond load/total fields convert to milliseconds, independently of local elapsed time; malformed completions never claim success. |
| Async state and persistence | Warmup reports active progress, completes separately from manual request history, persists after Runtime restart and does not dispatch on GET. |
| Overlap exclusion | An active preload rejects a second preload, manual metadata and LLM submission before another model request is sent. |
| Cancellation/deadline | A gated real HTTP request is cancelled or hits a real one-second provider cap; the local slot is released and no retry/unload request is sent. |
| Restart | An old running preload becomes interrupted/unconfirmed, without a remote request. |
| Full transport integration | The actual JavaScript `OllamaUI` saves `qwen3-coder:30b`; `RuntimeClient` preloads via the Python HTTP API, completes a 15-call mock Smoke run, then approves and rolls back. Preload is one separate native request; all 15 measured calls use the saved ID. All 15 call starts appear in the journal. |
| Journal retention/query | Concurrent writers maintain unique IDs and bounded retention. Filters/cursors, case-insensitive substring query and restart persistence pass. Query text is bound SQL data. |
| Redaction and storage failure | Common bearer/token/password/API-key values and structured prompt/content fields are removed; reasoning character counts remain useful metadata. An unavailable journal ignores writes and reports read errors. |
| API boundary | Missing local CSRF token/cross-origin access are rejected; duplicate/unknown query fields and excessive limits return 400; browser log floods return 429. Session tokens do not enter records. |
| Legacy/raw role logs | Existing logs remain read-only and previews are capped at the last 200,000 bytes. External symlinks are rejected; no role or model reruns occur. |
| GUI filters/pagination | Tests cover encoded queries, older-page accumulation, pausing while browsing history, JSONL export, stale evidence retention and ignoring responses from superseded filters. |
| GUI escaping | Record messages/details, API errors and raw role content are escaped; fabricated log levels/module metadata/cursors are rejected. |
| Actual app events | Sidebar navigation, Log form submission and warmup buttons reach the real event handlers. Log polling preserves focused search fields; warmup reads saved settings independently of an unsaved model draft. |
| Regression | Model-save persistence, streaming progress, split isolation, evidence tamper rejection, all budgets, approval/rollback, WSL setup, runtime cancellation and proxy bypass continue passing. |

Commands: `npm test`; `python3 -m unittest discover -s tests -p '*_test.py'`. Additional focused frontend, journal API and warmup tests were run after the final focus guard and storage/cleanup adjustments.

No requests were sent to the user's Windows Ollama service, and no Windows/GPU setup diagnostics were repeated. Browser-engine visual QA is unavailable in this managed environment; frontend validation uses JavaScript event/DOM and view tests, plus actual localhost HTTP integration. Windows native `server.log`, GPU-Z telemetry and external framework logs are not ingested. The static private Site ships the frontend; the local Python checkout must be updated/restarted for actual logging and preload execution.

See [user guide](../module-logs.md) for WSL upgrade and debugging steps.
