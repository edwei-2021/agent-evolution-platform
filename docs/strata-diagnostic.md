# Strata Compatibility Diagnostic (Strata 相容性診斷)

This is the first step toward a selectable Ollama / Strata provider. It adds a standalone diagnostic only. The GUI's provider settings, warmup and workflow dispatch remain unchanged until the target Windows / WSL evidence is reviewed.

## Reviewed implementation (已核對的實作)

The user's fork, [edwei-2021/Strata](https://github.com/edwei-2021/Strata), was reviewed at commit `61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406`. References:

- [serve/server.py](https://github.com/edwei-2021/Strata/blob/61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406/serve/server.py): OpenAI model/status endpoints, ordinary and streamed completions, tool argument deltas, authentication, request queue keep-alives and lazy loading.
- [docs/DETAILS.md](https://github.com/edwei-2021/Strata/blob/61b3fb5dd3f1e8ec09cf7e4e05208bc6d3c46406/docs/DETAILS.md): reasoning effort, API contracts and model lifecycle.
- [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking): Windows loopback and WSL NAT host addresses are different routing choices.

The provided endpoint is **`http://127.0.0.1:8081/v1`**. The script uses that literal URL by default. It never silently switches host or port. A successful Windows-local request does not establish WSL reachability. Run the diagnostic from the same WSL distribution that runs the GUI.

### Reuse a working ASK.py environment (沿用已驗證的 ASK 設定)

`ASK.py` reads its endpoint from `OPENAI_BASE_URL`, its key from `OPENAI_API_KEY` and its model from `STRATA_MODEL`. A diagnostic using the literal loopback default and `STRATA_API_KEY` is a different configuration. A WSL `ConnectionRefusedError` at `connect.started` tests only that chosen listener; it says nothing about the working environment's endpoint or Strata's API capabilities.

In the **same prepared WSL shell** where ASK works:

```bash
git pull --ff-only
python3 scripts/test_windows_strata.py --from-env --stage all --reasoning-effort none
```

This explicitly consumes those three environment variables. No environment file is opened or executed. Missing values and conflicting `--base-url`, `--host`, `--port`, `--model` or `--api-key-env` options fail before any request. The report names the configuration source and key variable, without recording the key. An explicit environment URL can contain a DNS hostname; DNS resolution runs inside the request worker's absolute deadline. There is no endpoint or credential fallback.

For metadata only use `--from-env --api-only`. To match ASK's single ordinary POST without metadata preflight, use `--from-env --stage chat --reasoning-effort none`. To test only the previously unverified tool exchange, use `--from-env --stage tools --reasoning-effort none`.

This mode reuses ASK's **endpoint/key/model**, not every generation option: `reasoning_effort=none` is explicit above, output defaults to 256 tokens and the diagnostic still sends `temperature=0`. Its connect and absolute request deadlines remain unchanged (ASK uses one longer socket timeout). A pass records the options actually tested.

## Run in stages (分階段執行)

Use the existing checkout; the script needs only Python's standard library. It is also usable as one downloaded Python file without the rest of the repository.

```bash
cd /mnt/d/agent-evolution-platform
git pull --ff-only
python3 scripts/test_windows_strata.py --api-only
```

Default / `--api-only` / `--stage metadata` sends only `GET /v1/models` and `GET /v1/status`. The latter is optional for older versions returning 404. Other errors, including authentication and connectivity failures, remain failures. The model ID list and available loaded/engine/context/activity/timing status are recorded. No generation request is sent. Metadata success is **`METADATA_ONLY_PASS`**, never a claim that a model can generate or use tools.

After metadata passes, copy the exact returned model ID, or use the already verified environment mode above:

```bash
python3 scripts/test_windows_strata.py --stage all --model '<exact-model-id>'
```

This performs the metadata checks, one ordinary text request, then a two-request streamed tool round trip. It has at most **three model request attempts**, stops at the first failed step and never retries. The tool echoes a synthetic test value and issues a fresh receipt inside the client: it cannot access files, run shell commands or use an MCP server. That receipt appears only in the tool result. The final answer must return the receipt and end without another tool call, proving more than repetition of the original user prompt. A length-truncated answer, malformed arguments, missing `[DONE]`, empty answer or repeated tool request cannot pass.

To run only an untested stage:

```bash
python3 scripts/test_windows_strata.py --stage chat --model '<exact-model-id>'
python3 scripts/test_windows_strata.py --stage tools --model '<exact-model-id>'
```

These stages skip metadata; supply the already verified model ID. `--interactive` provides a four-choice stage menu and asks for the model ID when generation is selected. It requires a terminal.

An explicit model alias is not rewritten to the first returned ID. The reviewed server's `model_for()` also serves request names beyond its listed aliases. If the chosen ID is absent from the list, the diagnostic records `requestedModelListed=false` and a warning; an actual generation must establish whether the server accepts it. Metadata alone never establishes alias usability.

### Thinking and output limits (Thinking 與輸出上限)

Defaults match the existing worker's important request fields: `temperature=0`, `max_tokens=256`, with `reasoning_effort` omitted. The reviewed Strata implementation uses its configured/shared/model default effort when omitted; its documented model default is `high`. A small output budget may therefore end in thinking or incomplete tool JSON. A `finish_reason=length` failure identifies this boundary rather than proving the transport is broken.

For a separately identified quick compatibility check, explicit controls are available:

```bash
python3 scripts/test_windows_strata.py --stage all --model '<exact-model-id>' \
  --reasoning-effort none --max-tokens 512 --timeout 120
```

The report freezes those options. Passing with them does not qualify a future GUI request that omits them; provider integration must preserve the verified effort and output budget.

### Explicit address override (明確指定連線位址)

If the default loopback fails under WSL NAT, first verify Strata's Windows listener / permitted host configuration. An explicit alternative is:

```bash
python3 scripts/test_windows_strata.py --host auto --port 8081 --api-only
```

`auto` reads the current WSL default IPv4 gateway; it is never an automatic fallback. An explicit `--host <Windows-IPv4>` is also supported. Keep the successful endpoint identical for later generation commands using the same address options. An HTTP 403 may involve Strata's allowed-host policy; 401 concerns its API key. The diagnostic does not modify either setting. It bypasses HTTP proxy environment variables and refuses redirects, including redirects to another host.

For an authenticated server, set `STRATA_API_KEY` locally (or name another variable with `--api-key-env`). The script reads it from the environment; there is no key argument or saved key. Without it, a fixed local placeholder is sent. Avoid pasting real credentials into a shared terminal transcript.

The explicit `--from-env` mode selects `OPENAI_API_KEY` even if `STRATA_API_KEY` is also set, matching ASK. Without that flag, ambient `OPENAI_BASE_URL` / `OPENAI_API_KEY` do not silently redirect the diagnostic or switch credentials.

## Evidence and deadlines (證據與期限)

Reports are stored under `.local/strata-tests/STRATA-<UTC-time>-<random>/`:

| File | Contents |
| --- | --- |
| `events.jsonl` | Request phases, host/port, HTTP status, elapsed time and periodic waiting observations |
| `report.json` | Script hash, reviewed source, endpoint, model/options, checks, capabilities, failures and local worker cleanup |
| Adjacent `.zip` | Both files, ready to attach for review |

The terminal prints `STRATA_TEST_STATUS` and `STRATA_TEST_SUPPORT`. Keep the ZIP even on failure. Reports include model identifiers, endpoint and a short synthetic-answer preview, but no complete prompts, model bodies, authorization headers or API key. Known HTTP error bodies are omitted. Reports do not enter the existing GUI support bundle; attach the separately printed Strata ZIP.

Default limits: TCP/TLS connect **5 seconds**, each metadata request **15 seconds absolute**, each model request **120 seconds absolute**. A request runs in one owned subprocess. On timeout or Ctrl+C the parent terminates/reaps that process, saves the last phase and exports evidence. Cleanup has bounded one-second waits. A slow/trickling body cannot renew the absolute deadline. This ends the local client; a remote request may continue temporarily. Waiting events establish client liveness, not model progress. Cold interpreter startup is included in each request's absolute limit.

Strata may respond to `stream=true` with ordinary JSON. The current production transport accepts this once without resending; the diagnostic does likewise and records `sse=false`. A tool round-trip pass through JSON does not claim SSE support.

Exit codes: `0` requested checks passed, `1` failed check, `2` invalid arguments, `3` report storage failure, `130` operator interruption. `CHAT_PASS` qualifies ordinary text; `TOOL_ROUNDTRIP_PASS` qualifies the synthetic tool exchange; `COMPATIBILITY_PASS` qualifies all selected API checks. None establishes benchmark quality or complete nanobot/GEPA workflow acceptance.

## Conditional integration (通過後的整合範圍)

After real WSL evidence passes, add an explicit Ollama / Strata choice and separate saved endpoint/model/effort settings. Freeze provider identity into each run. Use OpenAI model listing for Strata, not Ollama `/api/version` or `/api/tags`. Strata lifecycle/loaded status must use its own verified capability; never send Ollama's empty `/api/generate` preload to Strata. Preserve one-provider ownership, per-call/global budgets, cancellation, historical run identity and independent reviewer/approval gates. Qualify the resulting adapter with one focused real workflow before broader use.

Local verification uses a loopback HTTP fixture, never the user's Windows service. Run the focused tests with:

```bash
python3 -m unittest discover -s tests -p strata_diagnostic_test.py -v
```

No full M7 rerun, real GPU result or Windows acceptance is implied by local fixture success.
