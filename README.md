# Agent Evolution Platform

Evolution platform for bounded nanobot/GEPA Skill experiments, with a roadmap toward declarative workflow evolution and multiple runtimes (代理人演化平台).

## Intermediate Phase M delivery

New service components, Ubuntu migration, strict M1–M7 checks and debug support bundles are available. Read [the M operator guide](docs/intermediate-m.md) before moving an existing checkout or running acceptance. Component checks do not certify full phase completion; Docker/production closure remains explicit. The legacy GUI stays v0.7.1.

## Current status and authoritative roadmap

The implemented runtime baseline is **v0.7.1**. This documentation revision does not change the application version or certify new runtime tests.

Read the [revised development plan](docs/agent-evolution-platform-development-plan.md) for completed capabilities, remaining gaps, and the mandatory **Intermediate Phase M — Compatibility and Trust Hardening** before completing the production release path.

The plan supersedes earlier next-milestone scheduling: begin with canonical contracts and compatibility fixtures, then durable evidence and evaluator isolation, followed by dataset/comparison and complete release hardening. Existing Ollama configuration, preload, experiments, progress, logs and versions remain supported. OpenEvolve and additional runtimes follow these gates.

The existing repository was renamed to `edwei-2021/agent-evolution-platform` on 2026-10-12; repository identity and history are retained. Existing checkouts can keep their directory and update the Git origin URL. Current GitHub visibility is public; the private hosted GUI has separate access controls.

## Existing implementation and operational guides

GitHub: https://github.com/edwei-2021/agent-evolution-platform

Private GUI: https://skill-evolution-lab-edwei.edwei.chatgpt.site

Version **0.6.0** implements the first **nanobot SDK Python repair runner**（nanobot SDK Python 修復任務）. The new `#repair` page runs one version-pinned `nanobot-ai==0.3.5` worker with three caller-owned tools, a fresh workspace/session, frozen model/Skill/budgets, streaming tool-call evidence and an independent evaluator. The bounded integer-clamp fixture has six visible and six final cases; a model's pass claim never becomes a score. Read the source diff/tool trace and download a verified task patch. No Skill activation or repository patch application occurs automatically. [Runner guide](docs/nanobot-repair.md) · [Validation](docs/verification/nanobot-repair-validation.md).

The optional SDK is installed separately: stop the GUI, run `git pull --ff-only`, `bash scripts/install-nanobot.sh`, then `bash scripts/start-gui.sh`. The existing stdlib GUI environment, saved Windows Ollama port 11435/model, warmup, logs and version stores remain available. This installer downloads pinned packages/tokenizer cache only; it sends no Ollama requests or connection diagnostics.

Version **0.5.3** adds explicit model preloading and a persistent module log page（模型暖機與集中模組 Log）. Use **Preload model** in LLM Skills or Integrations before a cold model experiment. The separate asynchronous job calls native Ollama with an empty prompt, displays elapsed/loading time, and has its own saved provider timeout; it consumes none of the 15/101 experiment calls. **Module Log** (`#logs`) supports module/level/run filtering, search, older pages, current JSONL export and read-only role logs from older runs. The journal persists in `.local/debug.sqlite3`, retaining 10,000 records. [User guide](docs/module-logs.md) · [Validation](docs/verification/warmup-logs-validation.md).

Version **0.5.2** adds observable LLM inference and bounded waiting（LLM 回應進度與等待上限）. Model experiments receive SSE chunks, count completed requests separately from dispatched requests, and expose character counts, elapsed time, response timestamps and cancellation/error states. LLM Skills, rule Skills and the execution monitor share role-stage progress bars. Each model call defaults to a 120-second absolute limit, capped by saved provider settings and remaining run time; continuous chunks cannot extend it. [Progress validation](docs/verification/llm-progress-validation.md).

Version **0.5.1** fixes the Integrations model-save button（模型設定儲存修正）. Form submit buttons now reach their submit handlers before rendering; failed saves preserve typed fields. The page displays the backend's saved model ID and settings revision. Save a model once, then navigate to LLM Skills. Existing Windows Ollama port 11435 and endpoint settings are retained; no dependency installation or repeated connection diagnostics are required. [Fix validation](docs/verification/model-settings-save-validation.md).

GUI-first skill evolution workspace（技能演化 Web 工作台）. Version 0.5.0 adds **actual Ollama Skill execution and training-based reflection**: fresh model calls, one candidate, trusted output scoring, polling process visibility, human approval and immutable prompt versions. Its engine is `ollama-prompt-reflection-v1`, implemented here; the bounded nanobot SDK adapter is implemented in v0.6.0; GEPA 0.1.4 integration is implemented in v0.7.0. The earlier rule engine and synthetic demo remain separate. Windows Ollama defaults to 11435, GUI to 8765, both configurable. The WSL checkout and processing/temp/cache paths remain on D. No startup model calls or redundant Windows connection diagnostics are performed. This independent project does not modify MultiAgent-Evolution-Lab.

## WSL2 Ubuntu 24.04 / Python 3.11

In the WSL2 Ubuntu terminal, clone into `/mnt/d/agent-evolution-platform` (Windows `D:\agent-evolution-platform`), inspect first, install missing prerequisites, then start:

This repository is currently public. For authenticated contributions from WSL, use the [GitHub CLI browser-login instructions](docs/wsl-install.md#2-obtain-the-independent-project). The connected GitHub account in ChatGPT does not authenticate the WSL terminal, and GitHub account passwords cannot be used for HTTPS Git operations.

```bash
git clone https://github.com/edwei-2021/agent-evolution-platform.git /mnt/d/agent-evolution-platform
cd /mnt/d/agent-evolution-platform
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

## Ollama / Strata selection (模型服務選擇)

Integrations now offers separate saved Ollama and Strata profiles. In the same WSL shell where the Strata diagnostic passes, restart the GUI, choose **Strata**, check the suggested ASK environment values, and save. Strata uses OpenAI chat/tools/SSE, explicit reasoning effort and environment-only credentials; native loading uses its own API. Existing Ollama port 11435 is retained. See [provider setup and validation boundaries](docs/model-providers.md).

## Windows Ollama on port 11435 (Windows Ollama 連線)

The user has already verified Windows 10 Ollama metadata access from WSL2. This version incorporates that approach without repeating Windows setup or connection attempts: NAT gateway discovery, configurable port 11435, proxy bypass, metadata/inference socket timeouts 10/600 seconds and 256 output tokens. The supplied `--api-only` result proves metadata connectivity, not model generation.

```bash
cd /mnt/d/agent-evolution-platform
python3.11 scripts/configure_ollama.py --port 11435 --export-env
source .local/ollama/client.env
bash scripts/start-gui.sh
```

Open `http://localhost:8765/#integrations` to select an exact model ID and save settings. Reading/saving settings makes no Windows HTTP request. Model-list refresh and a single chat completion require explicit clicks. Provider records and settings stay under `.local/ollama/` on D; no extra Python packages are required. Rule-based Skill evolution remains separate; the LLM Skill page uses this provider. Full usage and preserved attachment tools: [Windows Ollama guide](docs/ollama-wsl.md).

## Actual LLM Skill evolution (LLM 技能演化)

After saving a model in **Integrations**, open `http://localhost:8765/#llm`. Start with Smoke (3/2/2 tasks, at most 15 model calls), or choose Full (20/10/20, at most 101 calls). The whole-run deadline defaults to 900 seconds. Coordinator freezes settings, Worker executes the baseline, Reflector uses training failures only, Evaluator runs and selects the candidate before held-out tests, and Reviewer recomputes scores from raw responses. Existing polling displays actual PIDs/status/logs; the LLM page shows calls, scores, body diffs, failures and immutable prompt versions.

Approve only a verified validation improvement with no held-out regression. A model release affects future model experiments; rule versions remain independent. Calls are not automatically retried. No nanobot/GEPA SDK adapter or model-quality claim is implied. Full workflow, limits and setup: [LLM Skill guide](docs/llm-skill-evolution.md).

## Measured local skill evolution (本機技能演化)

Open `http://localhost:8765/#skills` after starting the local server. Select up to four candidates, run search, review the actual validation/held-out evidence, then approve/activate or roll back a local version. Try your own text against the active Skill and export its `SKILL.md`. This phase requires no model key or new packages. The bounded target is `normalize-support-title`, with fixed Unicode/case/whitespace rules and a 20/10/20 handwritten dataset. Scores are measured task outputs; they do not represent LLM or GEPA performance. See the [skill evolution guide](docs/skill-evolution.md).

## Implemented

- Real Ollama Worker/Reflector prompt evolution, trusted task-output scores and 15/101-call profiles.
- Whole-run deadlines, cancellation, shared provider/workflow slots and raw request/response evidence.
- Separate immutable model Skills, human approval, rollback, history and Markdown export.

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

Agent records are editable browser-local role configurations. Their latest real native-tool run state appears as a separate telemetry overlay. The five initial records include planned orchestration, reflection, evaluation and review components; they are not five installed LLM runtimes. Framework-connected count remains zero; native tool processes are tracked separately in the execution monitor. GEPA is a version-pinned optimizer adapter over fresh nanobot tasks, not an external agent runtime. Changing these records does not change the fixed evolution simulation. See the [agent workspace guide](docs/agents-workspace.md).

Scores, tasks and events in **演化展示** are synthetic fixtures. **本機技能實驗** executes the bounded rule-search engine and stores actual outputs/evidence in SQLite and run artifacts. **執行監控** reads real process evidence for both workflow types. An Ollama provider and actual model Skill workflow are implemented; the bounded nanobot Python repair adapter is implemented. GEPA Skill-body optimization is implemented in v0.7.0; Hermes, Herdr, OpenClaw and NanoClaw execution adapters remain planned. Local measured Skill activation changes the server's active policy for future runs/trials; demo activation changes browser-only state. Neither operation publishes Git code or installs an external-agent Skill.

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
scripts/llm_engine.py    Model runner, prompt protocol and trusted evidence verification
scripts/llm_agents.py    Five supervised model-workflow roles
scripts/llm_store.py     Separate immutable prompt versions and approval
dist/js/llm-view.js      Actual model experiments, comparisons and version controls
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

## GEPA Skill optimization (技能最佳化)

Version **0.7.0** adds actual **GEPA 0.1.4 + nanobot 0.3.5** execution at `http://localhost:8765/#gepa`. Stop the GUI, pull the update, rerun `bash scripts/install-nanobot.sh`, restart and refresh. Begin with Smoke (4/2/4 grouped synthetic tasks), explicitly preload the saved model, then start search. Full uses 20/10/20 tasks with an 80-evaluation search cap. Only the Skill body changes; trusted tool/test evidence drives selection and final gates. Review the diff, approve a verified improvement, or roll back an immutable GEPA version. Existing rule/LLM versions remain separate. See [GEPA guide](docs/gepa-evolution.md), [how to read actual evolution results](docs/gepa-results.md) and [verification](docs/verification/gepa-validation.md).

## Accelerated workflow (加速流程)

**v0.7.1** retains all v0.7.0 features and adds structured per-step logs/timing at `http://localhost:8765/#steps`, a bounded batch evaluator and staged regression reports. Pull and restart the GUI; no new dependency is required. Use `.venv-nanobot/bin/python scripts/check_steps.py --profile quick` while editing and `--profile release` before publication. See the [accelerated delivery plan](docs/accelerated-plan.md) and [per-step verification](docs/verification/accelerated-validation.md). The evaluator microbenchmark was about 4.14× faster; this is not an Ollama inference-speed claim.

## Next milestone

Follow the revised development plan above. Complete Intermediate Phase M incrementally while retaining v0.7.1 capabilities: canonical contracts, durable event/lifecycle recovery, isolated evaluator, versioned datasets, safe feedback, per-task regression gates and complete release manifests. Then close Phase 4 and begin declarative workflow evolution.


## Verification

`npm test` verifies demo/registry behavior, polling transport, measured skill controls and stale-state boundaries. `python3 -m unittest discover -s tests -p '*_test.py'` verifies installer/HTTP behavior, real role processes, skill execution, evidence gates and immutable version persistence. See [LLM Skill verification](docs/verification/llm-skill-validation.md), [Ollama bridge verification](docs/verification/ollama-bridge-validation.md), [measured skill verification](docs/verification/skill-evolution-validation.md), [prior runtime verification](docs/verification/live-runtime-validation.md) and [installation verification](docs/verification/wsl-install-validation.md). Browser visual/full DOM QA and the user's WSL host were not directly tested. The fixture results support only the specified text-normalization contract; no LLM/GEPA performance claim is made.
