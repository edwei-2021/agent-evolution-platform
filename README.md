# nanobot GEPA MVP

GitHub: https://github.com/edwei-2021/nanobot-gepa-mvp

Private GUI: https://skill-evolution-lab-edwei.edwei.chatgpt.site

GUI-first skill evolution workspace（技能演化 Web 工作台）. Version 0.2.0 adds an editable agent registry, role/property/Skill inspection and a directed work relationship graph. Port 8765 remains the default, with `--port` for overrides. The documented WSL workspace is on Windows drive D, with project processing/temp/cache paths relative to that checkout. This is an interactive **demo**, with no model calls and no real evolution worker. It is an independent project; it does not modify MultiAgent-Evolution-Lab.

## WSL2 Ubuntu 24.04 / Python 3.11

In the WSL2 Ubuntu terminal, clone into `/mnt/d/nanobot-gepa-mvp` (Windows `D:\nanobot-gepa-mvp`), inspect first, install missing prerequisites, then start:

This repository is private. Before cloning, authenticate Git inside WSL through the [GitHub CLI browser-login instructions](docs/wsl-install.md#2-obtain-the-independent-project). The connected GitHub account in ChatGPT does not authenticate the WSL terminal, and GitHub account passwords cannot be used for HTTPS Git operations.

```bash
git clone https://github.com/edwei-2021/nanobot-gepa-mvp.git /mnt/d/nanobot-gepa-mvp
cd /mnt/d/nanobot-gepa-mvp
bash scripts/install-wsl.sh --check --python python3.11
bash scripts/install-wsl.sh --python python3.11
bash scripts/start-gui.sh
```

The `--check` command is read-only and returns exit code 1 when prerequisites or `.venv` are missing. Inspect its output before installing. Open `http://localhost:8765` in Windows. Installation reuses Python, fills missing APT tools, downloads verified project-local Node only when necessary, creates `.venv` without pip, and runs tests. Source, `.venv`, `.tools`, reports and subprocess temp/cache directories stay inside the checkout on D. Full instructions, private GitHub clone authentication, migration and troubleshooting: [WSL installation guide](docs/wsl-install.md).

## Run locally

No frontend dependencies or build step are required. Use a supported Linux Node major 22 / 24 / 26 for installer checks and Python 3.11+ for the static server. The WSL installer selects the interpreter; a standalone `npm run serve` uses whichever `python3` is on PATH.

```bash
npm test
npm run serve
```

Open `http://localhost:8765`. Serve files over HTTP; opening index.html directly will not load ES modules reliably. Localhost serving is intended for development. The hosted GUI uses private Sites access.

To choose another port (for example, 8766):

```bash
bash scripts/start-gui.sh --port 8766
# Standalone server alternative:
npm run serve -- --port 8766
```

Open `http://localhost:8766` when using that port.

## Implemented

- Agent workspace: configured/connected counts, five starter roles, search and role filtering.
- Agent details: Runtime/model, memory/isolation, step/temperature limits, tool names and assigned Skills.
- Browser-local agent creation/editing/deletion and directed relationship creation/deletion.
- Clickable relationship graph plus a table of sources, recipients, relationship types and deliverables.
- Skill body inspection follows the active Worker demo release; supporting Skills remain fixed examples.
- Existing schemaVersion 1 backups migrate to version 2 without losing experiments or releases.

- Traditional Chinese GUI: overview, skill evolution, evaluation records, demo releases, integration roadmap.
- Create experiments with evaluation budgets 40 / 80 / 120 and improvement / no-gain scenarios.
- Start, pause, resume, cancel; deterministic synthetic curves stop at their budget.
- Review baseline and candidate skill bodies, synthetic failure cases and held-out examples.
- Reject demo releases when there is no improvement or evaluation is incomplete.
- Create a local demo release and switch back to baseline.
- Browser localStorage persistence; refresh pauses unfinished runs.
- Validated JSON import/export; import replaces the local workspace and pauses active runs.
- Responsive layouts, keyboard navigation, modal forms, explicit demo labeling.

Agent records are editable browser-local role configurations, not discovered or running agents. The five initial records include planned orchestration, reflection, evaluation and review components; they are not five installed LLM runtimes. Connected count is zero. GEPA is a planned optimizer adapter, not a runtime. Changing these records does not change the fixed evolution simulation. See the [agent workspace guide](docs/agents-workspace.md).

All scores, tasks and execution events are synthetic fixtures. `S0` and `S1` are fixed example skill bodies. No nanobot, GEPA, Hermes, Herdr, OpenClaw or NanoClaw integration has been implemented. A GUI release changes only the browser's active version pointer, not a Git repository or agent installation.

## Source structure

```text
dist/index.html          Web application entry
dist/styles.css          Responsive dashboard styling
dist/js/app.js           Views and UI events
dist/js/domain.js        Pure demo state machine and validation
dist/js/adapter.js       Browser-local persistence adapter
dist/js/agents.js         Registry model, assignments and directed relationships
dist/js/agent-view.js     Agent details, graph and configuration form views
dist/js/agent-ui.js       Agent workspace interactions
tests/agents.test.js      Registry, migration, persistence and rendering boundaries
tests/domain.test.js     Lifecycle, release gate, import, persistence tests
tests/setup_test.py      Offline installer and real HTTP server tests
scripts/install-wsl.sh  Python selection and installer entry
scripts/setup_wsl.py    Environment check, missing tools and verification
scripts/start-gui.sh    Start with the project virtual environment
scripts/serve_gui.py    Loopback HTTP server for public assets only
docs/wsl-install.md     WSL2 installation and troubleshooting
docs/agents-workspace.md Agent workspace usage and data semantics
docs/architecture.md     Incremental implementation plan
docs/api-contract.md     Proposed backend contract (not implemented)
.openai/hosting.json     Private Site deployment identity
```

The tracked `dist/` folder is the canonical frontend source in this buildless MVP. Edit it directly. Do not add model credentials or GitHub tokens to frontend files, exported JSON or `.openai/hosting.json`.

## Persistence and remote use

The hosted URL can be accessed from a remote browser, subject to the owner's private sign-in. Records remain browser-local and do not sync across devices. Use JSON export/import to move demo records. If storage is unavailable, the GUI warns and retains changes in the current tab. Export before replacing a workspace. Concurrent browser tabs are independent; avoid editing the same workspace in several tabs.

## Next milestone

Implement FastAPI + SQLite with a job worker, nanobot execution adapter, trusted evaluator and GEPA optimizer. Replace DemoAdapter through the contract in `docs/api-contract.md`. Preserve this GUI and add explicit real/demo mode separation. Treat real publication and rollback as server-owned Git operations.

## Verification

`npm test` verifies the domain state machine, budget termination, release gates and import/persistence boundaries. `python3 -m unittest discover -s tests -p '*_test.py'` verifies installer behavior and the HTTP server. JavaScript syntax and static asset references are also checked during delivery. Browser visual QA was unavailable in the build environment; inspect desktop and mobile layouts during the first review. The v0.2.0 delivery has 28 JavaScript and 15 Python passing tests; see [agent workspace verification](docs/verification/agent-workspace-validation.md). WSL2 / Python 3.11 / live APT and Node downloads were not executed in the build environment; see [installation verification](docs/verification/wsl-install-validation.md). These checks provide no evidence of agent performance or evolution improvement.
