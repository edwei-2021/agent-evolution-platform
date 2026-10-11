# Windows Ollama Bridge (Windows Ollama 橋接)

Version 0.4.1 incorporates the user's working Windows 10 / WSL2 connection approach. It does not repeat host setup or automatically retest the Windows service. The provider transport is available for explicit single requests. Version 0.5.0 also connects it to [LLM Skill evolution](llm-skill-evolution.md); the older rule workflow remains independent.

## Recorded target evidence (實機驗證紀錄)

The user supplied terminal output from October 11, 2026 at 22:35:51, Asia/Taipei:

| Property | Observed value |
| --- | --- |
| WSL kernel / Python | `6.18.40.1-microsoft-standard-WSL2` / `3.11.9` |
| Host discovery | IPv4 default gateway, Windows 10 NAT assumption |
| Windows endpoint | `http://172.22.160.1:11435` |
| WSL source address | `172.22.166.226` |
| Ollama API version | `0.40.2` |
| TCP, version, native/OpenAI model listings | PASS |
| Models listed / loaded | 15 / none |
| Command | `python3 test_windows_ollama.py --port 11435 --api-only` |
| Result | `METADATA_ONLY_PASS`, exit 0, elapsed 0.559 seconds |
| Inference | Skipped by `--api-only`; model generation has not been demonstrated |

[Evidence summary](verification/ollama-user-evidence.json) is a transcription of supplied output, not the original diagnostic JSON. It records source attachment SHA-256 values and exact model IDs. The historical IP is evidence only: the provider resolves the current gateway when needed, unless an explicit IPv4 override is saved.

## Update without another connectivity test (更新設定，不重跑連線測試)

Use the existing checkout on D. No third-party Python dependency or model download is needed.

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --check --python python3.11
```

If the installer identifies missing prerequisites, run `bash scripts/install-wsl.sh --python python3.11`. It now includes `iproute2` for gateway discovery; it does not call Ollama or edit Windows settings.

Save settings and optionally generate client environment exports, without HTTP/TCP probes:

```bash
python3.11 scripts/configure_ollama.py --port 11435 --export-env
source .local/ollama/client.env
bash scripts/start-gui.sh
```

This leaves the model unselected. Open `http://localhost:8765/#integrations`, enter an exact installed model ID and save it. The recorded model IDs are historical suggestions, not an automatically refreshed list or a model usability claim.

If you have already chosen a model, add `--model <exact-model-id>` to the configuration command. You can change the Windows port with `--port`; change the GUI port separately through `bash scripts/start-gui.sh --port 8766`.

Leaving `--host` unspecified stores automatic gateway discovery. For an established address override, use `--host <Windows-IPv4>`. The provider requires exactly one distinct default IPv4 gateway in automatic mode; ambiguous routes/VPN configurations require an explicit override. It never guesses from DNS configuration or assumes WSL localhost forwarding.

Settings are saved to `.local/ollama/settings.json` inside the D-drive checkout. Explicit provider reports and client exports also remain under `.local/ollama/`. Existing settings survive GUI restarts. Exports are shell-quoted and atomically replaced. Regenerate exports after routing changes; the Python provider resolves automatic routing independently of old shell exports. A CLI configuration change is reflected after the GUI's **Reload settings** action.

## Web operations (Web 操作)

| Action | Windows network activity |
| --- | --- |
| Start GUI / enter Integrations / reload settings | None; reads saved settings, routes and historical evidence |
| Save settings | None; revision-checked local JSON update |
| Update model list | Explicit GET `/api/version`, `/api/tags`, `/v1/models` |
| Send one inference | Explicit POST `/v1/chat/completions` with the saved model and entered prompt |
| Existing rule Skill evolution / trial | None; continues to execute `local-rule-search-v1` |

There is no automatic metadata polling, inference preflight, model pull, retry, Windows server launch or firewall modification. All provider requests bypass proxy environment variables through `ProxyHandler({})`, matching the successful attachment.

Metadata socket timeout defaults to 10 seconds; inference socket timeout to 600 seconds; output budget to 256 tokens. The browser wait accommodates the configured inference timeout, rather than using the runtime polling client's 8-second limit. These are socket/wait limits, not a strict total execution deadline. Requests are non-streaming. One provider operation may run at a time; a duplicate operation returns HTTP 409 without sending another Ollama request. Closing the browser or a browser wait timeout does not cancel an already dispatched model request; reload local settings to inspect the eventual report. Requests are never automatically resubmitted.

Records separate `METADATA_ONLY_PASS`, `INFERENCE_PASS` and `FAIL`. They pin the settings revision, endpoint, model, timeout, output budget, timestamps and elapsed time. Only a nonempty visible chat response is an inference pass; this does not establish tool-use quality, task accuracy or evolution improvement. Reports include user prompts and model responses. A result from an earlier settings revision/endpoint is labeled accordingly. Historical evidence never becomes current live status automatically.

The GUI talks to its same-origin Python backend, which calls Windows Ollama. The browser does not call Windows Ollama directly, so no extra browser CORS configuration is needed. The existing loopback Host/Origin checks and local session token protect mutations. The private hosted static GUI does not execute this Python backend or reach the user's WSL machine; use the local URL above for these operations.

## Preserved attachment tools (保留的附件工具)

- `scripts/test_windows_ollama.py`: the uploaded diagnostic, preserved byte-for-byte. Its default still tests both inference APIs. Supply `--api-only` when only metadata is intended. This tool is optional and is never called by setup/start/provider configuration.
- `tools/ollama-wsl/`: the extracted ZIP contents, preserving the original README, validation record, checksums, Windows PowerShell script and WSL checker. The archived instructions document the original standalone package; they are not required daily startup steps for this project.

The original successful command can be reproduced, only when diagnostics are needed:

```bash
python3 scripts/test_windows_ollama.py --port 11435 --api-only \
  --out-dir .local/ollama/diagnostics
```

For a deliberate model test, choose an exact installed local model with `--model` and omit `--api-only`. This diagnostic makes two sequential inference calls (native and OpenAI-compatible); the Web single-request button makes only one OpenAI-compatible call. Do not rerun Windows bind/firewall configuration for an already working setup. If the WSL address later changes and connectivity actually fails, the preserved Windows script can refresh its scoped firewall rule using the correct distribution name.

## Next integration boundary (下一階段介面)

The bridge exposes reusable `OllamaBridge.request` transport and frozen configuration per request. Worker execution should consume the Skill body as model instructions, store actual task traces and evaluate outputs using trusted rules. Reflector candidate generation should use training feedback only. Pin provider/model/config and Skill/data/evaluator hashes for each experiment, keep validation and held-out data separate, and preserve human approval/rollback gates.

No nanobot or GEPA execution adapter is implemented by this bridge. Agent framework connection counts remain unchanged. Current rule-based scores are not LLM results.

References: [Microsoft WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking), [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), [Ollama FAQ](https://docs.ollama.com/faq). The implementation reuses the supplied proven client approach without changing the target Windows setup.

Version 0.5.0 implements the bounded Worker/Reflector execution path described above. It uses `ollama-prompt-reflection-v1`; GEPA/nanobot SDK adapters remain planned. See [LLM Skill evolution](llm-skill-evolution.md) for current controls, model protocol and evidence limits.
