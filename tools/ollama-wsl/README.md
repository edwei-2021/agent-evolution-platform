# Windows 10 Ollama Server to WSL2 Ubuntu

**Focused setup and verification guide（Windows Ollama 與 WSL2 Ubuntu 跨環境連線指南）**  
Prepared October 11, 2026. Reference port: **11435**.

## 1. Connection model（連線架構）

Run Ollama and store the models **on Windows**. Ubuntu in WSL2 acts as an HTTP client. For Windows 10 with WSL2 NAT, Ubuntu connects to the Windows IPv4 address shown as its default gateway（預設閘道）. The gateway can change after restarting WSL or Windows; detect it again instead of retaining an old IP. [1]

| Setting | Value in this guide |
| --- | --- |
| Windows server bind address（監聽位址） | `0.0.0.0:11435` |
| Windows local client URL | `http://127.0.0.1:11435` |
| WSL native API base URL | `http://<current Windows gateway>:11435` |
| WSL OpenAI-compatible API base URL | `http://<current Windows gateway>:11435/v1` |
| Reference installed model | `qwen3-coder:30b`; use another installed model if preferred |

Port **11435** preserves the earlier setup. Ollama's normal default is **11434**. You may use 11434 by supplying `-Port 11434` on Windows and `--port 11434` in WSL consistently. `0.0.0.0` specifies a server listening address; use a reachable Windows IP in client URLs. [2,3]

Windows 10 uses the NAT route documented here. Microsoft documents mirrored networking（鏡像網路）for Windows 11 22H2 and later, so this guide uses the gateway rather than WSL `localhost`. [1]

## 2. Files and prerequisites（檔案與必要條件）

| File | Purpose |
| --- | --- |
| `scripts/windows-ollama.ps1` | Check Windows, configure the server, add a WSL-scoped firewall rule, run a foreground server, restore settings |
| `scripts/wsl-connect.sh` | Run the WSL connection checker |
| `scripts/check-ollama.py` | Detect the gateway, check APIs/model ID, optionally perform inference, generate Bash exports |
| `VALIDATION.md` | Completed local checks and target-machine checks still required |
| `SHA256SUMS.txt` | Package file hashes |

Assume Windows 10 **22H2**, Windows PowerShell **5.1**, and an existing **WSL2 Ubuntu** distribution. Ollama's current Windows documentation requires Windows 10 22H2 or newer. [2]

In ordinary Windows PowerShell:

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,BuildNumber,OSArchitecture
wsl.exe --list --verbose
```

Confirm build `19045` or newer and `VERSION 2` for Ubuntu. The examples use `Ubuntu-24.04`; replace this with the exact name printed by `wsl.exe --list --verbose`. Extract the ZIP to a folder such as `C:\Users\YOUR_WINDOWS_USER\Downloads\ollama_windows10_wsl2`, then open PowerShell in that folder.

For script execution in each PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

This setting lasts only for that PowerShell process. Use the Windows account that owns the Ollama installation, including when elevating PowerShell for firewall changes.

## 3. Install and configure Windows Ollama（安裝與設定）

Download and run the official installer: <https://ollama.com/download/windows>. After installation, reopen PowerShell so its PATH includes Ollama. Existing installations can skip installation. [2]

```powershell
ollama --version
.\scripts\windows-ollama.ps1 -Action configure -Port 11435
```

The script backs up the original user `OLLAMA_HOST` once, then sets:

```text
OLLAMA_HOST=0.0.0.0:11435
```

The script changes no model/context settings. An already-running server keeps its previous environment. Quit Ollama from its system tray menu before starting the server below. [3]

### Start one foreground server（前景執行）

In an ordinary PowerShell window, run:

```powershell
.\scripts\windows-ollama.ps1 -Action serve -Port 11435
```

Keep this window open. `Ctrl+C` stops the server. This action sets the process environment explicitly, so it works even if the terminal was opened before the user setting changed. It refuses to start if TCP 11435 is already occupied and does not terminate existing processes.

For normal daily use, you may instead restart the Ollama tray application after configuration. Verify the listener using the next section. Run one server per port; use either the tray server or the foreground server for this endpoint.

## 4. Check Windows and allow the WSL connection（Windows 驗證與防火牆）

In a **second** ordinary PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows-ollama.ps1 -Action check -Port 11435
Get-NetTCPConnection -State Listen -LocalPort 11435 |
    Select-Object LocalAddress,LocalPort,OwningProcess
curl.exe --noproxy "*" http://127.0.0.1:11435/api/version
curl.exe --noproxy "*" http://127.0.0.1:11435/api/tags
```

Expect a listener on `0.0.0.0:11435` and JSON API responses. A listener on `127.0.0.1` alone does not accept the WSL NAT connection. An empty model list still proves that the API is reachable.

Open PowerShell **as Administrator**, in the same package folder and with the same Windows account:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows-ollama.ps1 -Action firewall -Port 11435 -Distro Ubuntu-24.04
```

This creates/refreshes one named Windows Firewall allow rule, scoped to the Ollama executable, TCP port 11435, Windows gateway IP, and the current WSL source IP. It uses `Profile Any` so the WSL virtual network's profile classification does not prevent the scoped connection. It does not disable the firewall or edit other rules.

Because the rule uses the current WSL source IP, rerun this action after a WSL/Windows restart if the IP changes. Existing broad Ollama allow rules can independently permit other clients; this script does not narrow or remove them. For a restricted deployment, inspect existing Ollama rules in Windows Defender Firewall with Advanced Security.

### Make a model available（準備模型）

In the second ordinary PowerShell window, point the CLI at the local Windows endpoint:

```powershell
$env:OLLAMA_HOST = 'http://127.0.0.1:11435'
ollama list
# Only if the reference model is not already installed:
ollama pull qwen3-coder:30b
ollama list
curl.exe --noproxy "*" http://127.0.0.1:11435/v1/models
```

Pulling this model requires sufficient Windows storage and memory for inference. An existing smaller model can verify the same network path; use its exact listed model ID. This process-level CLI URL does not change the saved server bind setting.

## 5. Connect from WSL2 Ubuntu（WSL 連線）

In Ubuntu, install only the client-side tools used by this guide:

```bash
sudo apt-get update
sudo apt-get install -y python3 curl iproute2
```

The package can be used directly from its Windows folder, including paths with spaces:

```bash
cd '/mnt/c/Users/YOUR_WINDOWS_USER/Downloads/ollama_windows10_wsl2'
bash scripts/wsl-connect.sh --port 11435 --model qwen3-coder:30b
source ./ollama-wsl.env
```

The checker discovers the current gateway using `ip -j -4 route show default`. It directly probes `/api/version`, `/api/tags`, and `/v1/models`, bypassing HTTP proxy settings for these checks. If a model is supplied, it must be listed by both model APIs. It writes `ollama-wsl.env` only after all requested checks pass.

Expected output format (the IP is illustrative):

```text
Endpoint: http://172.22.160.1:11435
PASS native API; server version: <installed version>
PASS model listing: qwen3-coder:30b
PASS export file: <absolute path>/ollama-wsl.env
```

Load the generated exports in the shell that runs your client. The file contains only shell-safe exports; it is separate from diagnostic output.

```bash
printf '%s\n' "$OLLAMA_BASE_URL" "$OPENAI_BASE_URL" "$OLLAMA_MODEL"
curl --noproxy '*' -fsS "$OLLAMA_BASE_URL/api/tags"
curl --noproxy '*' -fsS "$OPENAI_BASE_URL/models"
```

| Generated variable | Meaning |
| --- | --- |
| `OLLAMA_HOST` | Client URL for an Ollama CLI, if a CLI is present in WSL |
| `OLLAMA_BASE_URL` | Native HTTP API root, without `/v1` |
| `OPENAI_BASE_URL` | OpenAI-compatible root ending in `/v1` |
| `OPENAI_API_KEY` | `ollama`, a local client placeholder; Ollama ignores this value for local compatibility endpoints [4] |
| `OLLAMA_MODEL` | Exact model ID, when `--model` was supplied |
| `NO_PROXY`, `no_proxy` | Existing exclusions plus localhost and the detected Windows IP |

The WSL `OLLAMA_HOST` is for a client connecting to Windows. Do not use that client environment to launch a second Ollama server in WSL.

### Verify a real inference request（驗證實際推論）

```bash
bash scripts/wsl-connect.sh --port 11435 \
  --model qwen3-coder:30b --infer --timeout 600
source ./ollama-wsl.env
```

Expect `PASS inference:` followed by a nonempty response. The checker does not require the model to obey the exact word `OK`; it verifies an actual chat response. First inference may include model loading and take longer than a metadata request. A successful model list alone does not prove that the model can load and generate.

For an explicit host override or a different export location:

```bash
bash scripts/wsl-connect.sh --host YOUR_WINDOWS_IPV4 --port 11435 \
  --model qwen3-coder:30b --env-file "$HOME/ollama-wsl.env"
source "$HOME/ollama-wsl.env"
```

Use the override only when you have established the reachable Windows address. `--host` accepts IPv4 addresses. If custom routing/VPN changes the default gateway, inspect `ip -4 route show default` and the Windows virtual adapter IP first.

## 6. Daily sequence（每日使用順序）

1. Start the Windows Ollama tray server or the foreground `serve` action.
2. Open Ubuntu. If the WSL IP changed, refresh the Windows firewall action.
3. Run `bash scripts/wsl-connect.sh --model qwen3-coder:30b` and source the generated export file.
4. On the first setup or after changing models, add `--infer` to verify actual generation.

Repeat discovery after restarting Windows, running `wsl --shutdown`, or changing VPN/network routing. Source the freshly generated file in each client shell. Reusing an old generated IP can fail after a restart.

## 7. Troubleshooting and restore（排除問題與還原）

| Symptom | Check/action |
| --- | --- |
| `ollama` is not found on Windows | Reopen PowerShell after installation. The script also checks `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. |
| Windows API fails | Check server startup, port, listener, and `%LOCALAPPDATA%\Ollama\server.log`. [2] |
| Windows API works; WSL connection is refused | Confirm the server listens on `0.0.0.0`, the gateway is correct, and both sides use 11435. |
| Windows API works; WSL request times out | Refresh the scoped firewall rule. Inspect VPN/security software or a managed firewall policy. |
| Address already in use | Use `-Action check`; inspect the owning process. Quit the tray server before choosing foreground mode. |
| Model missing / HTTP 404 during inference | Run Windows `ollama list`; use the exact ID or pull the model on Windows. |
| APIs work; inference fails or times out | Read the Windows server log and inspect model memory/loading. Network connectivity has already been established. |
| WSL restarted and connection stopped working | Refresh the firewall rule and regenerate/source `ollama-wsl.env`. |
| Client uses a proxy for the Windows IP | Source the generated `NO_PROXY` exports, or use `curl --noproxy '*'` for the explicit checks. |

Inspect a firewall rule in Administrator PowerShell:

```powershell
Get-NetFirewallRule -Name Ollama-WSL-Bridge-11435 | Get-NetFirewallAddressFilter
Get-NetFirewallRule -Name Ollama-WSL-Bridge-11435 | Get-NetFirewallPortFilter
```

To restore the original saved user bind setting and remove this package's rule, first stop the foreground server or quit the tray app, then run in Administrator PowerShell:

```powershell
.\scripts\windows-ollama.ps1 -Action restore -Port 11435
```

Restart Ollama afterward. The backup is retained for repeat restore. If you created rules for several ports, remove the package's named rules for those other ports separately. Open a fresh Ubuntu shell without sourcing the generated file to return to your usual client environment.

## 8. Acceptance criteria and references（驗收與參考）

The target setup is verified when Windows local APIs respond, WSL reaches the same server version and model ID, and WSL receives a nonempty chat completion. Record the Ollama version, current gateway, port, and exact model ID. These new scripts have local client QA; they still require execution on your Windows 10/WSL2 host. See `VALIDATION.md`.

1. Microsoft: [Accessing network applications with WSL](https://learn.microsoft.com/en-us/windows/wsl/networking).
2. Ollama: [Windows](https://docs.ollama.com/windows), [official installer](https://ollama.com/download/windows).
3. Ollama: [FAQ — server environment and bind configuration](https://docs.ollama.com/faq).
4. Ollama: [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).
