# Nanobot Python Repair Runner (nanobot Python 修復 Runner)

Release **v0.6.0** implements roadmap Phase 2c's first local vertical slice. The application imports the actual **nanobot-ai 0.3.5** Python SDK. One SDK Worker repairs a bounded fixture; the surrounding roles perform trusted preparation, trace summary, evaluation and review. This stage fixes the Skill rather than evolving its body. GEPA integration is the next milestone.

## Install and start (安裝與啟動)

Stop the current GUI with Ctrl+C, then use the existing WSL checkout:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-nanobot.sh
bash scripts/start-gui.sh
```

The optional installer creates `.venv-nanobot` using the GUI's Python and installs the exact resolved versions in `requirements-nanobot.txt`. It also prepares the `cl100k_base` tokenizer cache. Downloads/temp/cache stay in project `.local/` paths on D; the existing `.venv`, provider settings, port 11435, versions and run evidence are retained. Python 3.11+ is required. The dependency set was executed on Linux Python 3.12; installed package metadata was also checked for Python 3.11 compatibility, without claiming a 3.11 runtime test.

This command installs packages and public tokenizer data; it does not send model requests, pull models or rerun Windows connection diagnostics. It imports the SDK only. Do not launch `nanobot webui` or `gateway` for this integration: the application uses the Python SDK directly and retains its own GUI port 8765.

Refresh `http://localhost:8765/#repair` with Ctrl+Shift+R and confirm v0.6.0. The page shows whether the pinned SDK environment imports successfully. If SDK setup is unavailable, the original GUI, model Skills, rule Skills, warmup and logs remain usable. Stop/restart the GUI after installation so its environment inspection refreshes.

## Run one repair (執行一次修復)

1. Keep the exact Ollama model saved in Integrations. For cold models, click **Preload model** first and wait for its successful record.
2. Set model call budget (2–12, default 8), whole-run cap (60–7200 seconds, default 900) and call cap (10–3600 seconds, default 120). Each call is further bounded by saved provider timeout and remaining run time. Set an adequate saved output-token cap for tool arguments/source.
3. Click **Start Python repair**. Submission freezes model/settings, fixed Skill metadata/body, tool grants, fixture/evaluator/adapter hashes and SDK version.
4. Watch actual stages, completed/dispatched calls, received characters/tool-argument characters, elapsed/remaining time and logs. The workflow/provider slots prevent overlapping model experiments, preload or manual provider operations.
5. After completion, click **Read repair and trace** to compare source and tool outcomes, then download the task patch. Full files remain in the run directory.

The fixture is `integer-clamp-v1`: repair only `clamp(value, lower, upper)` in `solution.py`. Integer bounds are inclusive; reversed bounds raise `ValueError`. Six public cases are available through `run_tests`. Six final cases remain in trusted evaluator code, outside agent tools, and execute after the SDK turn ends and source is frozen. This tiny fixture verifies the runner/evidence contract; it does not demonstrate general Python repair ability or optimization quality.

## Runtime and tool contract (執行與工具)

| Stage | Actual operation |
| --- | --- |
| Coordinator | Prepare fresh workspace/source; freeze inputs and measure public baseline |
| Worker | Real `Nanobot(AgentLoop(...)).run(...)`, fresh session key, `ephemeral=True`, fixed model and Skill |
| Reflector | Summarize recorded tool outcomes without another model request or Skill mutation |
| Evaluator | Execute trusted public/final tests on baseline and frozen candidate; produce diff |
| Reviewer | Replay stream/request/tool evidence and recompute test results; no inference or activation |

The SDK is installed separately, while the GUI supervisor remains stdlib-only. A version-pinned `BoundedLoop` overrides the 0.3.5 default-tool registration seam, using a caller-owned registry containing exactly:

| Tool | Allowed operation |
| --- | --- |
| `read_solution` | Read exactly `solution.py` in this run's workspace |
| `write_solution` | Replace that same file after bounded AST validation |
| `run_tests` | Run the fixed public tests through the trusted evaluator command |

Shell, arbitrary file paths, network tools, cron, MCP and spawn tools are not registered. Symlink/path escape is rejected. Fresh session/workspace state and explicit SDK construction avoid normal user config/history. Browser agent relationships/tools/temperature remain configuration; they do not grant permissions or alter this fixed runner. The frozen run displays its actual model, Skill and adapter separately.

The evaluator supports a pure integer-function subset: one exact function signature, bounded constants/nodes/source, comparisons, conditionals, local assignments, return, `min`/`max` and `ValueError`. Imports, attributes, nested functions, recursion, loops, comprehensions, classes, decorators and arbitrary calls are rejected. Accepted source executes with restricted builtins under `python -I -S`, 2 CPU seconds, a 256 MB address-space cap and a parent wall-time limit. This is a narrow validated language/evaluator boundary, not container isolation for arbitrary Python. Broader repository repair requires a stronger OS/container sandbox before enabling shell execution.

The custom SDK provider receives the frozen exact model ID and uses the established no-proxy OpenAI-compatible endpoint with bounded SSE function-call deltas. Actual physical request attempts are counted before dispatch; every SDK model request, including any SDK finalization/context work, passes through the same budget. The provider's own transient/persistent retry loops are bypassed. Corrective agent turns may request another bounded call; HTTP/malformed-completion errors stop the workflow without transport retries. Caller cancellation terminates the local process group; already dispatched Ollama inference may continue remotely.

Native provider usage is retained when reported. SDK estimates, if any, remain labeled separately; output-character counts are not tokens. The model tag is pinned, not an immutable model weight digest. Dependency versions are pinned, while the tested implementation boundary is SDK 0.3.5 and adapter/fixture code provenance.

## Evidence and outcome (證據與結果)

Artifacts under `.local/runs/RUN-.../` include frozen `repair-config.json`, requests/raw SSE and normalized replies (`repair-calls.json`), tool arguments/results (`repair-tools.json`), SDK result/usage/messages, baseline/candidate source, public/final evaluations, a unified patch and reviewer evidence hashes. The `nanobot` journal module records bounded metadata; role stdout is available through the existing log page.

Reviewer checks call accounting/model/grants, reconstructs SSE replies, relates executed tools to recorded model requests, replays writes/visible test results, checks candidate bytes against the final workspace file and recomputes trusted measurements. A model saying “all tests passed” cannot produce success without matching test outputs. A completed, verified workflow can still have **repairPassed: false**; operational completion and task success are distinct.

No new Skill version is created, no LLM/rule active pointer changes, and no patch is applied to the source repository automatically. Read-only evidence preview is capped by the existing 200,000-character API limit; larger raw files remain available in WSL. The private hosted Site publishes the frontend; local execution and evidence require the localhost API.

After an application code/fixture upgrade, old unapproved runs whose frozen provenance no longer matches may require a new run. Already stored versions/settings and original evidence remain preserved.

## Next milestone (下一階段)

Use this frozen runner/evaluator contract for a real GEPA adapter that evolves only the Skill body, with independent grouped training/validation/final data and explicit review/version activation. Remote authenticated workers and arbitrary multi-file repair are separate later work.

Primary sources: [nanobot Python SDK](https://github.com/HKUDS/nanobot/blob/v0.3.5/docs/python-sdk.md), [0.3.5 release](https://github.com/HKUDS/nanobot/releases/tag/v0.3.5), and pinned SDK source contracts in `nanobot/agent/loop.py`, `nanobot/providers/base.py`, `nanobot/agent/tools/base.py`.
