# LLM Progress and Deadline Validation (LLM 進度與等待上限驗證)

Release: **v0.5.2**. Linux development runtime, Python 3.12.14 and Node 24.19.0. No new dependencies.

## Reported symptom and scope (問題與修正範圍)

The supplied screenshot showed call 1/15 in `running` state while polling had succeeded 101 times. The old counter represented dispatched calls, not completed calls. Model requests used non-streaming responses and could wait for the saved 600-second socket timeout. The screenshot establishes successful GUI polling, but cannot establish whether the Windows model was loading, queued, computing or stalled.

New model runs request OpenAI-compatible SSE from the established Ollama endpoint. The worker publishes first/last chunk timestamps and observed answer/reasoning character counts; the browser continues to poll the local API. Before the first chunk the UI states that it is waiting and cannot distinguish loading, queueing or inference. No partial answer or reasoning text is rendered in the progress panel. Received SSE events and assembled answers are retained in local evidence for independent review.

A new frozen single-call absolute deadline defaults to 120 seconds, capped by saved provider settings and remaining run time. Users may configure 10–3600 seconds before a run; the whole workflow remains bounded at 60–7200 seconds (default 900). Both the transport and supervisor enforce call bounds, including when chunks continue arriving. Timeouts fail the run with the call number and effective limit. Cancellation and timeout finalize the last call after the worker stops, release the local provider slot and send no additional requests.

LLM Skills, rule Skills and the execution monitor now display completed role stages, elapsed time, backend heartbeat and polling freshness. LLM pages additionally distinguish dispatched, completed and failed requests; show the current task/split, call elapsed/remaining time and response activity; and provide an indeterminate waiting bar. The call denominator is an upper budget, so a valid completed 13/15 no-gain run remains 13/15. Paused or stale snapshots stop animation and explicitly report freshness. Progress updates preserve focused forms.

## Verification (驗證)

| Scenario | Evidence |
| --- | --- |
| Complete SSE workflow | Actual loopback HTTP plus supervised subprocesses complete all 15 Smoke calls, reconstruct JSON responses, count reasoning separately and pass reviewer verification. |
| In-flight response | A gated first reasoning chunk is visible while the call remains running; completed count is 0, dispatched count is 1, and heartbeats continue. |
| Silent model | A real one-second saved provider cap terminates a blocked first request promptly, surfaces call #1's effective limit and sends one request only. |
| Continuously arriving chunks | A loopback server emits reasoning every 100 ms. The absolute one-second call deadline still stops it before completion; no subsequent requests occur. |
| Supervisor deadline | Fault injection expires the first active call while its socket remains open. The supervisor stops the process and finalizes failure evidence without another dispatch. |
| Whole-run deadline | Existing fault-injection coverage confirms the workflow deadline stops a waiting worker and releases its provider slot. |
| Cancellation | The current call becomes cancelled after process termination, zero completions are reported and no later calls occur. |
| Disconnect/protocol errors | Missing `[DONE]`, malformed JSON/deltas/finish reasons, provider stream errors, invalid UTF-8 and excessive output fail without retry or false completion. |
| Compatible JSON response | A server ignoring SSE is consumed once; no second fallback request is sent. Existing JSON mock workflows and full 101-call accounting continue to pass. |
| Evidence tampering | Reviewer reconstructs visible answers from retained SSE events; altered stream content blocks approval. |
| Frontend progress | Tests cover 0/15 with request #1 active, real elapsed/remaining time, response characters/timestamp, stale/paused animation, escaped errors, frozen terminal time and valid 13/15 completion. All three relevant pages contain accessible progress panels. |
| Focused input | Real app event listeners update only the progress region while an input has focus, preserving its connected form and draft fields. |
| Submission | The optional single-call limit is validated before dispatch and frozen with the existing immutable request body; uncertain submissions are not automatically retried. |

Commands: `npm test` and `python3 -m unittest discover -s tests -p '*_test.py'`. **66 JavaScript and 67 Python tests passed, 133 total.**

These are actual localhost transport/subprocess tests and JavaScript event/view tests. Browser-engine visual QA and the user's Windows GPU/model latency were not tested. No Windows diagnostics or requests were repeated. Existing port 11435, gateway discovery, proxy bypass, persisted model settings and version approval remain intact. Disconnecting the local worker does not guarantee that Ollama stops an already dispatched generation on the model server.

## Apply in WSL (WSL 更新)

Stop the GUI with Ctrl+C, then update the existing checkout and restart:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/start-gui.sh
```

Use Ctrl+Shift+R at `http://localhost:8765/#llm` and confirm **v0.5.2**. Start a new Smoke run. During the first pending request, the panel must show completed 0/15 and dispatched 1, a timer, call limit and waiting/response activity. For a cold 30B model that legitimately needs longer, raise the next run's single-call limit within the saved provider cap. This upgrade does not install dependencies or require another connection diagnostic. Restart interrupts any existing active run; the streaming/deadline configuration applies to newly submitted runs.

The private hosted Site receives the updated frontend. The local Python backend must also be updated and restarted using the commands above; the static Site does not reach WSL automatically.

Protocol reference: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).
