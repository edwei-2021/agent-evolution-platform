# Ollama / Strata provider selection

The GUI supports two separately saved model-service profiles. Existing Ollama settings retain port 11435 and are not silently replaced. Selecting a draft does not activate it; saving changes the active provider and increments its revision. Reads, selection, saving and GUI startup send no model-service requests. Active model operations prevent settings changes.

## Strata setup (Strata 設定)

Use the same prepared WSL shell in which this command has already passed:

```bash
python3 scripts/test_windows_strata.py --from-env --stage all --reasoning-effort none
```

The shell must export `OPENAI_BASE_URL`, `STRATA_MODEL` and `OPENAI_API_KEY`. Stop the previous GUI, update the checkout and start it in that shell:

```bash
git pull --ff-only
bash scripts/start-gui.sh
```

Open `http://localhost:8765/#integrations` and select **Strata**. On a first visit, valid ASK environment settings supply suggestions for the base URL and model. Previously saved Strata settings take precedence. Check these fields before saving:

| Field | Meaning |
| --- | --- |
| Base URL | The exact URL that passed the WSL diagnostic, including `/v1`; do not substitute Windows loopback for the tested WSL address |
| Model | Exact tested model/request alias; never replaced with the first listing entry |
| Key environment variable | `OPENAI_API_KEY` by default; enter the variable name, never the key |
| Reasoning effort | `none` by default, matching the explicit compatibility test |
| Maximum output tokens | 256 by default; preserve the tested value initially |
| Metadata / inference timeout | Existing saved bounds apply; no automatic retries or deadline increases |

The GUI inherits exported variables at process start. If credentials are missing, restart it in the prepared shell. Keys are read only from that environment, never returned in settings or written to profiles/reports. Runs store a key digest to reject credential changes between role processes. Changing endpoint, model, effort or provider requires a new run. Provider requests bypass proxies and Strata requests refuse redirects.

## Focused next operation (下一個實際操作)

No need to repeat successful diagnostic requests. After saving, perform one **Python 修復實驗** with the pinned nanobot SDK ready. Inspect the worker's tools, independent evaluator and reviewer, and terminal status. A successful API exchange does not guarantee a model can complete the bounded task. `max_iterations`, a deadline or malformed tools remain failures.

Optional explicit controls are independent:

| Action | Ollama | Strata |
| --- | --- | --- |
| Model-list refresh | `/api/version`, `/api/tags`, `/v1/models` | `/v1/status`, `/v1/models` |
| One chat | OpenAI chat completion | Authenticated OpenAI chat completion with saved effort |
| Preload | Empty `/api/generate`, requested keep-alive | Explicit `/v1/load`; server manages retention |

Preload confirms loading only, not generation. Strata's load endpoint is implemented from the reviewed server contract and locally tested; the supplied real compatibility test did not call it. With Strata auto-load enabled, the next real workflow can load as part of inference. Cancelling preload reaps the local worker and releases its slot; remote loading may continue. No unload is sent.

Switching back to Ollama restores its own saved profile after saving. Each new LLM, nanobot repair and GEPA run freezes provider kind, endpoint, revision, model, effort and limits. Shared call ownership, independent scores, approval and rollback gates remain enforced. Explicit M scripts use the same frozen configuration and record it in model-policy identity; Docker evaluation remains mandatory and is not qualified by GUI fixture tests.

## Diagnostics and verification scope

Existing `.local/diagnostics/ollama.jsonl` now also holds explicit Strata setting/metadata/chat events; the legacy filename/API route is retained for compatibility. Warmup and workflow/model-call logs retain their separate files. Download the existing diagnostic ZIP after a failure; it includes the new provider-helper source hash. See [runtime diagnostics](runtime-diagnostics.md).

Local tests use authenticated loopback servers and real pinned nanobot/GEPA SDK processes. They exercise profile isolation, credential drift, JSON/SSE, fragmented tool arguments, independent review, approval, rollback and tamper rejection. Existing warmup tests enforce timeout/cancellation and finalizer cleanup. No Windows GPU service or Docker was available inside that verification environment. The supplied `COMPATIBILITY_PASS` establishes the real API boundary; the integrated GUI's real-model workflow still needs its own result. This is not a full M7 acceptance claim.

Focused tests:

```bash
python3 -m unittest discover -s tests -p provider_switch_test.py -v
.venv-nanobot/bin/python -m unittest discover -s tests -p strata_workflow_test.py -v
node --test tests/ollama-ui.test.js tests/warmup-client.test.js tests/app-forms.test.js
```

The SDK fixture module expands into real role subprocesses, the pinned optimizer/runner, model transport, tool execution, immediate trusted replay, evaluator replay, reviewer replay and approval verification. It reuses the source-owned calibrated workflow budgets, per-call bounds and cleanup allowances; it changes no limits or M7 selection. Optional SDK tests explicitly skip when pins are absent, so inspect skips before claiming coverage. In restricted offline verification, use the project's prepared tokenizer cache or a pre-dispatch network guard; never treat a blocked download as model evidence.
