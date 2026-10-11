# WSL2 Ubuntu 24.04 installation（安裝與啟動）

This installs the current GUI demo and its development checks. It does not install or execute nanobot, GEPA, a model server or a real evolution backend. The GUI has no Python third-party dependencies, npm packages, build step or model API key requirement.

## 1. Verify WSL2 in Windows

In Windows PowerShell:

```powershell
wsl --list --verbose
```

Confirm that the Ubuntu 24.04 distribution has `VERSION` = `2`. Open that Ubuntu terminal. The Linux installer also checks the kernel for WSL2; custom kernels may need explicit manual verification.

## 2. Obtain the independent project

Keep the checkout in the Ubuntu filesystem, for example under `~/projects`. If Git is missing, install the clone prerequisites first:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends git ca-certificates
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/edwei-2021/nanobot-gepa-mvp.git
cd nanobot-gepa-mvp
```

The repository is private. The connected GitHub account in ChatGPT does not sign in Git inside WSL. Use your existing Git HTTPS credential manager or configured GitHub SSH authentication. For SSH, replace the clone URL with `git@github.com:edwei-2021/nanobot-gepa-mvp.git`. Do not put access tokens into the clone URL, scripts or logs. If Git access is not configured, download the repository ZIP through your signed-in GitHub browser and extract it inside Ubuntu; version metadata in the local installation report will then be null until a Git checkout is used.

For an existing checkout, save/commit your own changes, then update:

```bash
git pull --ff-only
```

## 3. Inspect the environment before installation

```bash
bash scripts/install-wsl.sh --check --python python3.11
```

This performs a read-only check. It does not install packages, create a virtual environment, download Node or write a report file. Exit code `0` means ready; `1` means missing prerequisites or a target mismatch. A first run can legitimately report `.venv: not ready` and return `1`. Check all printed errors before running the installer.

Machine-readable inspection:

```bash
bash scripts/install-wsl.sh --check --python python3.11 --json
```

For a Python installed by Conda, pyenv or another provider, supply the actual executable:

```bash
bash scripts/install-wsl.sh --check --python /absolute/path/to/python3.11
```

`--python` accepts one executable, not shell code. Without it, the launcher first chooses `python3.11`, then `python3`. Python 3.11 or newer is required; the report shows the interpreter actually selected. The installer will not install/downgrade Python or change `/usr/bin/python3`.

## 4. Install missing dependencies and verify

```bash
bash scripts/install-wsl.sh --python python3.11
```

The installer:

1. Confirms Ubuntu 24.04, WSL2, x86_64/aarch64, Python 3.11+ and frontend assets.
2. Checks installed APT package status and executables. Installs only missing `git`, `curl`, `ca-certificates`, `xz-utils` and `tar`; asks for sudo only when needed. It does not run a full system upgrade.
3. Reuses a supported Linux Node runtime (major 22, 24 or 26). If missing/unsupported, downloads pinned Node **22.23.3** from nodejs.org into `.tools/`, checks the official SHA-256 manifest before extraction, and verifies the executable version. Windows `node.exe` is not accepted. The checksum checks downloaded-file integrity; it is not separate GPG verification. Global Node and shell startup files are untouched.
4. Creates `.venv` with the selected Python using `--without-pip`. No Python packages are required in this GUI phase. If the venv module is missing, installs the corresponding versioned venv package only if an APT candidate already exists; it does not add PPAs. A custom Python with no such package must be repaired through its original provider.
5. Rechecks readiness, runs JavaScript and Python tests, and writes `.local/environment.json` after all checks pass. The report contains versions, paths and current Git commit, not credentials. Runtime directories are ignored by Git.

Repeat the same command safely: supported existing tools and a compatible `.venv` are reused. An incompatible/incomplete `.venv` or incomplete pinned Node installation is reported, not deleted. Move the indicated directory aside yourself after inspection, then retry. Python version 3.11 is supported by the source; delivery validation was performed on Python 3.12 because no 3.11 interpreter was available in the build environment.

## 5. Start the GUI

```bash
bash scripts/start-gui.sh
```

Open **http://localhost:8080** in the Windows browser. Microsoft documents Windows-to-WSL applications through localhost; VPN, localhost-forwarding settings or custom WSL networking can affect access. The server binds to `127.0.0.1`, serves only `dist/`, and does not expose the repository root, reports or credentials. Use Ctrl+C to stop.

If port 8080 is occupied:

```bash
bash scripts/start-gui.sh --port 8081
```

Then open http://localhost:8081. The current local server is for development and has no login, API worker or LAN exposure. For remote access now, use the private hosted GUI linked in README. This installer does not change Windows firewall or WSL network settings.

## Update and repeat checks

```bash
git pull --ff-only
bash scripts/install-wsl.sh --python python3.11
bash scripts/start-gui.sh
```

Stop the old server before restarting after an update. GUI records remain in browser localStorage and are tied to the origin (scheme/host/port); `localhost:8080`, `localhost:8081` and the hosted site each have separate stores. Export/import JSON when moving between them.

## Troubleshooting

| Observation | Action |
| --- | --- |
| `Python executable not found` | Run `command -v python3.11`; provide the interpreter path with `--python`. |
| Python 3.10 or older | Select an existing Python 3.11+; do not replace Ubuntu's system interpreter. |
| WSL2 kernel not detected | Verify `wsl --list --verbose` in Windows. `--allow-non-wsl` is an explicit escape for Ubuntu 24.04 VM/container validation, not automatic WSL conversion. |
| APT sudo/network error | Repair sudo rights or Ubuntu package/network configuration, then rerun. |
| Node download/checksum failure | The installer stops before publishing the tool directory; check proxy/DNS/HTTPS and retry. |
| Existing `.venv` mismatch | Inspect it and move it aside; rerun with the same intended interpreter. |
| Browser cannot connect | Check the server terminal, chosen port, then WSL localhost-forwarding/network configuration. |
| `Address already in use` | Stop the old server or use `--port 8081`. |

## References

- Node.js 22.23.3 LTS release and Linux binaries: https://nodejs.org/en/blog/release/v22.23.3
- Python 3.11 venv / --without-pip: https://docs.python.org/3.11/library/venv.html
- Microsoft WSL networking: https://learn.microsoft.com/en-us/windows/wsl/networking
