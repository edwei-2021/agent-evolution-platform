# nanobot GEPA MVP

GitHub: https://github.com/edwei-2021/nanobot-gepa-mvp

Private GUI: https://skill-evolution-lab-edwei.edwei.chatgpt.site

GUI-first skill evolution workspace（技能演化 Web 工作台）. Version 0.4.1 adds an explicit Windows Ollama bridge (default 11435), server-owned settings, reusable OpenAI-compatible transport and optional single-request Web trials. Startup and configuration do not probe Windows; the supplied metadata evidence is preserved. Version 0.4.0 introduced **measured local skill evolution**: training-only rule search, actual task-output evaluation, candidate curves/diffs, human approval, immutable SQLite versions, rollback and live skill trials. Its engine is `local-rule-search-v1`, implemented here; nanobot/GEPA evolution adapters remain planned. The earlier `python-fix-and-verify` simulation remains separately labeled. Port 8765 is the default with `--port` overrides; the WSL checkout and processing/temp/cache paths stay on D. This independent project does not modify MultiAgent-Evolution-Lab.

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

## Windows Ollama on port 11435 (Windows Ollama 連線)

The user has already verified Windows 10 Ollama metadata access from WSL2. This version incorporates that approach without repeating Windows setup or connection attempts: NAT gateway discovery, configurable port 11435, proxy bypass, metadata/inference socket timeouts 10/600 seconds and 256 output tokens. The supplied `--api-only` result proves metadata connectivity, not model generation.

```bash
cd /mnt/d/nanobot-gepa-mvp
python3.11 scripts/configure_ollama.py --port 11435 --export-env
source .local/ollama/client.env
bash scripts/start-gui.sh
```

Open `http://localhost:8765/#integrations` to select an exact model ID and save settings. Reading/saving settings makes no Windows HTTP request. Model-list refresh and a single chat completion require explicit clicks. Provider records and settings stay under `.local/ollama/` on D; no extra Python packages are required. Existing rule-based Skill evolution is separate and does not yet call this provider. Full usage and preserved attachment tools: [Windows Ollama guide](docs/ollama-wsl.md).

## Measured local skill evolution (本機技能演化)

Open `http://localhost:8765/#skills` after starting the local server. Select up to four candidates, run search, review the actual validation/held-out evidence, then approve/activate or roll back a local version. Try your own text against the active Skill and export its `SKILL.md`. This phase requires no model key or new packages. The bounded target is `normalize-support-title`, with fixed Unicode/case/whitespace rules and a 20/10/20 handwritten dataset. Scores are measured task outputs; they do not represent LLM or GEPA performance. See the [skill evolution guide](docs/skill-evolution.md).

## Implemented

- Windows Ollama bridge: persisted endpoint/model/timeouts, WSL gateway discovery and proxy bypass.
- Manual Web metadata update and single inference, pinned request reports and historical target evidence.
- Preserved uploaded diagnostic and Windows/WSL setup tools; no automatic target probes or inference.

- Measured rule-based Skill search and candidate curves/diffs; all training probes are counted.
- Frozen skill/data/evaluator/runner/runtime hashes, actual task traces and held-out release checks.
- Server-owned version approval, activation/rollback, optimistic revision checks and Skill export/trials.

- Live execution monitor: default 2-second polling, interval selection, refresh, pause/resume polling and workflow cancellation.
- Actual local tool-agent processes: asset hashes, JavaScript/Python tests, evidence analysis and review artifacts.
- PID, process liveness, start/end times, exit codes, output tails, events and SQLite run history.
- Live status overlays on agent lists, details and graph nodes; stale snapshots are explicitly marked.

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

Agent records are editable browser-local role configurations. Their latest real native-tool run state appears as a separate telemetry overlay. The five initial records include planned orchestration, reflection, evaluation and review components; they are not five installed LLM runtimes. Framework-connected count remains zero; native tool processes are tracked separately in the execution monitor. GEPA is a planned optimizer adapter, not a runtime. Changing these records does not change the fixed evolution simulation. See the [agent workspace guide](docs/agents-workspace.md).

Scores, tasks and events in **演化展示** are synthetic fixtures. **本機技能實驗** executes the bounded rule-search engine and stores actual outputs/evidence in SQLite and run artifacts. **執行監控** reads real process evidence for both workflow types. An explicit Ollama provider bridge is implemented; no nanobot, GEPA, Hermes, Herdr, OpenClaw or NanoClaw execution adapter has been implemented. Local measured Skill activation changes the server's active policy for future runs/trials; demo activation changes browser-only state. Neither operation publishes Git code or installs an external-agent Skill.

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
dist/js/runtime-client.js Live HTTP/polling client and stale-state handling
dist/js/runtime-view.js   Live process/evidence monitor
dist/js/skill-view.js     Measured candidates, review, versions and trials
scripts/ollama_bridge.py Windows Ollama transport and server-owned settings
scripts/configure_ollama.py Offline endpoint settings and shell exports
scripts/test_windows_ollama.py Preserved attachment diagnostic
tools/ollama-wsl/         Preserved ZIP tools and original instructions
dist/js/ollama-ui.js      Explicit Ollama settings and single-request controls
docs/ollama-wsl.md        Integrated Windows Ollama usage and boundaries
scripts/runtime_service.py SQLite history and process supervisor
scripts/native_agents.py Fixed project-health tasks
scripts/skill_engine.py  Declarative Skill executor and training-only search
scripts/skill_agents.py  Fixed skill-search/evaluation/review role tasks
scripts/skill_store.py   Immutable versions and revision-checked activation
skills/title-normalizer/ Fixed baseline and 20/10/20 task dataset
tests/skill_test.py      Actual skill processes, evidence gates and version/API tests
tests/skill-client.test.js Skill HTTP/controller and rendering regressions
tests/runtime_test.py     Actual processes, API policy and workflow integration
tests/runtime-client.test.js Polling, live mutations and stale snapshots
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
docs/api-contract.md     Implemented local API and future adapter contracts
docs/skill-evolution.md  Measured skill workflow, evaluation and boundaries
.openai/hosting.json     Private Site deployment identity
```

The tracked `dist/` folder is the canonical frontend source in this buildless MVP. Edit it directly. Do not add model credentials or GitHub tokens to frontend files, exported JSON or `.openai/hosting.json`.

## Persistence and remote use

The hosted URL can be accessed from a remote browser, subject to the owner's private sign-in. Sites serves static assets and does not execute this Python supervisor: use the WSL localhost interface for live execution. A hosted browser does not automatically connect to your WSL machine. Registry/demo records remain browser-local; measured skills/runs live in the local server SQLite store. Use JSON export/import to move demo records, and back up server `.local/` with the service stopped for measured evidence. If storage is unavailable, the GUI warns and retains changes in the current tab. Export before replacing a workspace. Concurrent browser tabs are independent; avoid editing the same workspace in several tabs.

## Next milestone

Local process monitoring, measured declarative skill evolution and an explicit Ollama provider bridge are implemented. Use the bridge for isolated nanobot model-task execution and GEPA reflective search behind the frozen skill/evaluation contracts, followed by authenticated remote access. The local rule engine is a dependency-free integration foundation, not a GEPA implementation. Keep model secrets server-side and preserve trusted release/rollback gates.

## Verification

`npm test` verifies demo/registry behavior, polling transport, measured skill controls and stale-state boundaries. `python3 -m unittest discover -s tests -p '*_test.py'` verifies installer/HTTP behavior, real role processes, skill execution, evidence gates and immutable version persistence. See [Ollama bridge verification](docs/verification/ollama-bridge-validation.md), [measured skill verification](docs/verification/skill-evolution-validation.md), [prior runtime verification](docs/verification/live-runtime-validation.md) and [installation verification](docs/verification/wsl-install-validation.md). Browser visual/full DOM QA and the user's WSL host were not directly tested. The fixture results support only the specified text-normalization contract; no LLM/GEPA performance claim is made.
