# Nanobot Repair Runner Validation (nanobot 修復 Runner 驗證)

Release: **v0.6.0**. Linux Python 3.12.14, Node 24.19.0. Actual installed **nanobot-ai 0.3.5** and the exact resolved dependencies in `requirements-nanobot.txt`; no SDK mocks. Model responses use actual loopback HTTP mocks, never the user's Windows Ollama service.

## Integration boundary (整合範圍)

The roadmap's first local Phase 2c slice is implemented: one fixed Python fixture, one actual SDK Worker, caller-owned tools and trusted evaluation/review. The SDK constructor, `AgentLoop`, tool registry, Tool subclasses, provider response/usage types and lifecycle were verified against the pinned package and source. The 0.3.5 default-tool registration seam is overridden so ungranted shell/network/spawn/MCP tools never enter the registry. The custom provider bypasses transient/persistent retry wrappers while routing every physical request through frozen budgets and bounded SSE transport.

The fixture evaluator accepts only the specified pure-function AST subset under a trusted isolated command/resource limits. This is not a general arbitrary-Python OS sandbox, a real GEPA implementation or a general repair-quality benchmark. The bounded Skill is immutable during this phase.

## Verified scenarios (驗證項目)

| Scenario | Evidence |
| --- | --- |
| Real SDK repair | Real SDK performs read/write/test tools and finishes; 4 model requests, 3 tool operations and 12/12 trusted cases pass. Model ID/temperature/grants are pinned. |
| Independent scoring | An assistant immediately claiming all tests passed without edits completes its turn but receives `repairPassed:false` from actual evaluator outputs. |
| Hidden isolation | All recorded model requests exclude final-case inputs; final tests run after the SDK exits and source freezes. Agent tools expose public tests only. |
| Unsafe code | Imports, attributes, loops, recursive calls and huge-exponent expressions are rejected before executing candidate code. Fixed names/signature and bounded source/nodes/constants apply. |
| Tool replay and tampering | Reviewer relates executed tools to recorded model calls, replays source writes/public test output and reconstructs streamed tool arguments. Altered stream/tool evidence blocks verification. |
| Newline preservation | CRLF candidate source is preserved and independently replayed/scored with matching source/patch evidence. |
| No HTTP retry | A provider HTTP 503 produces exactly one physical request and fails the worker; SDK wrappers cannot resend it. |
| Call cap | A model repeatedly requesting reads stops at the frozen 2-call cap; SDK finalization cannot dispatch another request. |
| Deadline/cancellation | A blocked model request hits a real one-second saved cap or user cancellation; the actual SDK process group stops, its shared provider slot releases and no later requests occur. Preload is rejected while the repair owns the slot. |
| Actual Web client/API | Real JavaScript `RuntimeClient` submits through the Python HTTP API, polls SDK completion, validates 12/12 results and reads verified source/tool/patch artifacts. LLM approval rejects this task; version pointers stay unchanged. |
| Missing SDK/invalid options | Invalid integer bounds fail before dispatch; the stdlib environment rejects missing SDK cleanly without a model request or leased slot. |
| GUI | Actual app listeners navigate/start the Python page. Tests cover disabled/stale/active gates, immutable uncertain submissions, fixed score denominators, impossible progress/results, escaping and preview truncation. |
| Regression | Existing model-save, preload, module logs, SSE Skill evidence, evaluation isolation, versions, proxy bypass, WSL setup and supervisor cases continue passing. |

Commands:

```bash
npm test
python3 -m unittest discover -s tests -p '*_test.py'
.venv-nanobot/bin/python -m unittest discover -s tests -p '*_test.py'
```

**81 JavaScript and 91 Python tests passed (172 total). The complete Python suite ran in the actual SDK environment with no skipped SDK tests.** Focused frontend checks also passed after the final descriptive UI changes. The stdlib suite intentionally skips SDK-only integration when the optional package is absent; those tests are run without skips in the actual SDK environment. Installed package `Requires-Python` metadata was checked against Python 3.11; execution was on Python 3.12, not the user's WSL host.

Browser-engine visual QA is unavailable in this managed environment. Frontend validation uses event/DOM and view tests plus real loopback client/API integration. No Windows model, GPU performance, firewall, gateway or connection diagnostics were repeated. Published Sites assets are static frontend files; WSL must update/install the optional SDK/restart to execute this stage.

See [runner guide](../nanobot-repair.md) for installation, scope and next GEPA milestone.
