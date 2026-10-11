# nanobot GEPA MVP

GitHub: https://github.com/edwei-2021/nanobot-gepa-mvp

Private GUI: https://skill-evolution-lab-edwei.edwei.chatgpt.site

GUI-first skill evolution workspace（技能演化 Web 工作台）. Version 0.1.0 implements an interactive **demo**, with no model calls and no real evolution worker. It is an independent project; it does not modify MultiAgent-Evolution-Lab.

## Run locally

No frontend dependencies or build step are required. Use Node.js 20+ for tests and Python 3 for the static server.

```bash
npm test
npm run serve
```

Open `http://localhost:8080`. Serve files over HTTP; opening index.html directly will not load ES modules reliably. Localhost serving is intended for development. The hosted GUI uses private Sites access.

## Implemented

- Traditional Chinese GUI: overview, skill evolution, evaluation records, demo releases, integration roadmap.
- Create experiments with evaluation budgets 40 / 80 / 120 and improvement / no-gain scenarios.
- Start, pause, resume, cancel; deterministic synthetic curves stop at their budget.
- Review baseline and candidate skill bodies, synthetic failure cases and held-out examples.
- Reject demo releases when there is no improvement or evaluation is incomplete.
- Create a local demo release and switch back to baseline.
- Browser localStorage persistence; refresh pauses unfinished runs.
- Validated JSON import/export; import replaces the local workspace and pauses active runs.
- Responsive layouts, keyboard navigation, modal forms, explicit demo labeling.

All scores, tasks and execution events are synthetic fixtures. `S0` and `S1` are fixed example skill bodies. No nanobot, GEPA, Hermes, Herdr, OpenClaw or NanoClaw integration has been implemented. A GUI release changes only the browser's active version pointer, not a Git repository or agent installation.

## Source structure

```text
dist/index.html          Web application entry
dist/styles.css          Responsive dashboard styling
dist/js/app.js           Views and UI events
dist/js/domain.js        Pure demo state machine and validation
dist/js/adapter.js       Browser-local persistence adapter
tests/domain.test.js     Lifecycle, release gate, import, persistence tests
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

`npm test` verifies the domain state machine, budget termination, release gates and import/persistence boundaries. JavaScript syntax and static asset references are also checked during delivery. Browser visual QA was unavailable in the build environment; inspect desktop and mobile layouts during the first review. These checks provide no evidence of agent performance or evolution improvement.
