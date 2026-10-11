# WSL2 Ubuntu 24.04 installation（安裝與啟動）

This installs the GUI, local native-tool runtime supervisor and development checks. It does not install or execute nanobot, GEPA, a model server or a real Skill evolution optimizer. The GUI has no Python third-party dependencies, npm packages, build step or model API key requirement.

## 1. Verify WSL2 in Windows

In Windows PowerShell:

```powershell
wsl --list --verbose
```

Confirm that the Ubuntu 24.04 distribution has `VERSION` = `2`. Open that Ubuntu terminal. The Linux installer also checks the kernel for WSL2; custom kernels may need explicit manual verification.

## 2. Obtain the independent project

Use `/mnt/d/nanobot-gepa-mvp` as the project root (Windows `D:\nanobot-gepa-mvp`). Confirm `/mnt/d` is mounted and writable. The repository is private: the connected GitHub account in ChatGPT does not authenticate Git inside WSL. Authenticate in WSL before cloning.

Install Git and GitHub CLI, then start browser authentication. When running as `root`, omit `sudo` from the APT commands:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends git gh ca-certificates
gh auth login --hostname github.com --git-protocol https --web
```

Use the URL and one-time code displayed in the terminal to complete authentication in the Windows browser. Sign in as GitHub user `edwei-2021` (or another account granted repository access). If WSL cannot launch a browser, open the displayed URL manually. Complete login before continuing. Do not share the code or credentials in chat.

Configure Git to use the authenticated CLI, verify repository access, then clone:

```bash
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
gh repo view edwei-2021/nanobot-gepa-mvp --json nameWithOwner,isPrivate
git clone https://github.com/edwei-2021/nanobot-gepa-mvp.git /mnt/d/nanobot-gepa-mvp
cd /mnt/d/nanobot-gepa-mvp
```

Run authentication, credential setup and clone as the same Linux user: `root` and a regular Ubuntu user have separate credential configuration. GitHub account passwords are not accepted for HTTPS Git operations. If using manual HTTPS authentication, the username is the GitHub login (`edwei-2021`), and the password prompt requires a personal access token. The browser flow above avoids manually copying a token. Do not put tokens in clone URLs, project files or logs.

An existing Git HTTPS credential manager or configured SSH authentication is also supported. For SSH, replace the clone URL with `git@github.com:edwei-2021/nanobot-gepa-mvp.git`. Alternatively, download the repository ZIP through your signed-in GitHub browser and extract it into `/mnt/d/nanobot-gepa-mvp`; installation report version metadata will be null until a Git checkout is used.

Project paths follow the checkout location:

| Data or processing | Default location |
| --- | --- |
| Git checkout and public assets | `/mnt/d/nanobot-gepa-mvp` and `dist/` |
| Project Python environment | `/mnt/d/nanobot-gepa-mvp/.venv/` |
| Downloaded Node runtime and staging | `/mnt/d/nanobot-gepa-mvp/.tools/` |
| Installer/test/GUI temporary files | `/mnt/d/nanobot-gepa-mvp/.local/tmp/` |
| Subprocess cache locations | `/mnt/d/nanobot-gepa-mvp/.local/cache/` |
| Environment report | `/mnt/d/nanobot-gepa-mvp/.local/environment.json` |
| GUI launch working directory | `/mnt/d/nanobot-gepa-mvp` |

Installer subprocesses receive project-local TMPDIR/TMP/TEMP and cache settings. APT packages and the existing base Python remain managed by Ubuntu; the installer does not relocate the operating system. GUI demo records still use browser localStorage; export JSON to a directory under `D:\nanobot-gepa-mvp` when a file backup on D is needed. Runtime directories are excluded from Git.

To migrate an older checkout, first commit/push any source changes you want to preserve. Clone afresh into the D location and rerun installation there; create a new `.venv` in the destination. Python virtual environments are tied to their creation paths. Keep the old checkout until the new one works. For an existing D checkout, save/commit your own changes, then update:

```bash
cd /mnt/d/nanobot-gepa-mvp
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
4. Creates `.venv` with the selected Python using `--copies --without-pip`. No Python packages are required in this GUI phase. If the venv module is missing, installs the corresponding versioned venv package only if an APT candidate already exists; it does not add PPAs. A custom Python with no such package must be repaired through its original provider.
5. Rechecks readiness, runs JavaScript and Python tests, and writes `.local/environment.json` after all checks pass. The report contains versions, paths and current Git commit, not credentials. Runtime directories are ignored by Git.

Repeat the same command safely: supported existing tools and a compatible `.venv` are reused. An incompatible/incomplete `.venv` or incomplete pinned Node installation is reported, not deleted. Move the indicated directory aside yourself after inspection, then retry. Python version 3.11 is supported by the source; delivery validation was performed on Python 3.12 because no 3.11 interpreter was available in the build environment.

## 5. Start the GUI

```bash
cd /mnt/d/nanobot-gepa-mvp
bash scripts/start-gui.sh
```

Open **http://localhost:8765** in the Windows browser. Microsoft documents Windows-to-WSL applications through localhost; VPN, localhost-forwarding settings or custom WSL networking can affect access. The server binds to `127.0.0.1`, serves only `dist/`, and does not expose the repository root, reports or credentials. Use Ctrl+C to stop.

The default port is **8765**. You can choose another port at startup, including when the default is occupied:

```bash
bash scripts/start-gui.sh --port 8766
```

Then open http://localhost:8766. The current local server is for development, binds to loopback and has no account login or LAN exposure. It provides a same-origin native-tool API protected by a local mutation token. The private hosted GUI can display configuration/demo pages, but cannot run or reach the WSL Python supervisor automatically. This installer does not change Windows firewall or WSL network settings.

Open **執行監控** and choose **執行專案檢查** to launch the fixed real tool workflow. Status polling defaults to 2 seconds. Logs and SQLite history stay under the project `.local/` directory on D. See [live runtime operation](live-runtime.md). No new third-party dependencies are needed; the doctor checks Python `sqlite3`/`fcntl` support and runtime source files.

## Update and repeat checks

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --python python3.11
bash scripts/start-gui.sh
```

Stop the old server before restarting after an update. GUI records remain in browser localStorage and are tied to the origin (scheme/host/port); `localhost:8765`, `localhost:8766` and the hosted site each have separate stores. If you previously used `localhost:8080`, export records from that origin and import them at the new address. Export/import JSON when moving between them.

## Troubleshooting

| Observation | Action |
| --- | --- |
| `Invalid username or token` / `Password authentication is not supported` | Use `gh auth login --hostname github.com --git-protocol https --web`, then `gh auth setup-git --hostname github.com`, under the Linux user doing the clone. Account passwords do not work for Git HTTPS. |
| `gh repo view` cannot access the private repository | Check `gh auth status --hostname github.com` and authenticate with an account granted access to `edwei-2021/nanobot-gepa-mvp` before cloning. |
| `Python executable not found` | Run `command -v python3.11`; provide the interpreter path with `--python`. |
| Python 3.10 or older | Select an existing Python 3.11+; do not replace Ubuntu's system interpreter. |
| WSL2 kernel not detected | Verify `wsl --list --verbose` in Windows. `--allow-non-wsl` is an explicit escape for Ubuntu 24.04 VM/container validation, not automatic WSL conversion. |
| APT sudo/network error | Repair sudo rights or Ubuntu package/network configuration, then rerun. |
| Node download/checksum failure | The installer stops before publishing the tool directory; check proxy/DNS/HTTPS and retry. |
| Existing `.venv` mismatch | Inspect it and move it aside; rerun with the same intended interpreter. |
| Browser cannot connect | Check the server terminal, chosen port, then WSL localhost-forwarding/network configuration. |
| `Address already in use` | Stop the old server or use `--port 8766`. |

## References

- GitHub command-line authentication: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github#authenticating-with-the-command-line
- GitHub CLI browser login: https://cli.github.com/manual/gh_auth_login
- Configure Git credentials through GitHub CLI: https://cli.github.com/manual/gh_auth_setup-git
- Node.js 22.23.3 LTS release and Linux binaries: https://nodejs.org/en/blog/release/v22.23.3
- Python 3.11 venv / --without-pip: https://docs.python.org/3.11/library/venv.html
- Microsoft WSL networking: https://learn.microsoft.com/en-us/windows/wsl/networking
