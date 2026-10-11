# Agent Workspace — v0.2.0 (代理人工作區)

Open the **代理人** page after updating the project. It is now the default landing page. The same interface runs locally at `http://localhost:8765` and on the existing private hosted Site.

## Counts and initial roles (數量與初始角色)

The registry starts with five editable role configurations. **已設定代理人** counts registry records; **實際連線** counts framework connections and remains zero. In v0.3.0, a separate native-tool supervisor supplies real PID/state overlays and the execution monitor; nanobot/GEPA adapters are still not connected. Configured agents can be enabled or disabled without launching or stopping a process. Skills count distinct assigned Skill IDs across agents. Relationships count directed handoff definitions.

| Record | Role (角色) | Assigned Skill | Planned integration |
| --- | --- | --- | --- |
| Orchestrator | Coordination and scheduling (協調與排程) | `plan-evolution-run` | Scheduling service |
| nanobot Worker | Task execution (任務執行) | `python-fix-and-verify` | nanobot runner |
| Skill Reflector | Skill reflection (技能反思) | `reflect-skill` | GEPA optimizer adapter |
| Evaluator | Evaluation and verification (評估與驗證) | `evaluate-python` | Trusted Python evaluator |
| Release Reviewer | Release review (版本檢閱) | `review-release` | Review service |

These are logical components of the planned workflow, not five installed LLM agents. GEPA is an optimizer. Evaluation and review may be implemented as services or human review in a later release.

## Inspect and edit (檢閱與編輯)

1. Search agent names, IDs, roles, Runtime names, model names, tool names or Skill IDs. Use the role filter to narrow the list. The relationship graph still shows the complete registry.
2. Select a list row or graph node. The detail panel shows role, Runtime/model, memory/isolation configuration, step limit, temperature, connection state, tool identifiers and assigned Skills.
3. Select a Skill to read its description, version and body. The path shown is a logical Skill path; this release does not create or load Runtime `SKILL.md` files.
4. Choose **編輯設定** or **新增代理人**. Model values are names only; do not enter API keys. Tool identifiers do not grant permissions. Maximum steps and temperature are metadata in this release.
5. Deleting a configuration removes its incident relationships after confirmation. It leaves experiments and demo releases intact.

The Skill catalog contains five fixed examples. `python-fix-and-verify` is the first-round evolution target. Its body follows the active demo release or baseline after rollback. The other Skill bodies remain fixed. Assigning additional Skills or changing roles does not change the current synthetic evolution simulation.

## Directed work relationships (有方向的工作關係)

Arrow direction is **source → recipient**. Click a node to highlight its incoming and outgoing edges. The relationship table is the complete text alternative to the graph and lists the deliverable for every handoff. On narrow screens, scroll the graph horizontally; the detail panel moves below the graph.

Four relationship types are available: task delegation (任務委派), evaluation evidence (評估證據), reflection feedback (反思回饋), and release review (版本檢閱). A feedback loop is allowed. The initial loop sends training evidence from Evaluator to Skill Reflector and a candidate Skill back to Worker; held-out tasks are excluded from reflection by the proposed design. This is a design annotation, not an implemented evaluator boundary.

Choose **新增關係**, select source/recipient/type, and describe the deliverable. Self-links, duplicate source/recipient/type tuples and absent endpoints are rejected. A relationship can be deleted from the table. The registry supports at most 30 agents and 120 relationships. Work relationship edits describe intended collaboration; they do not dispatch tasks or create execution traces. v0.3.0 overlays the latest native-tool process state on list/detail/graph nodes, matched by agent ID. The fixed project-health workflow does not execute the configured graph; consult [live runtime operation](live-runtime.md) for its actual stage order.

## Storage and upgrades (儲存與升級)

Agent configurations and relationships share the existing browser-local workspace with experiments and releases. Export JSON to back up configuration, demo experiments and demo releases (not server execution history), preferably under `D:\nanobot-gepa-mvp`. Import replaces the current workspace after confirmation and pauses running demo experiments.

Existing schemaVersion 1 data is migrated in memory to version 2 with the five starter roles. Experiments, release bodies and active version are preserved. New exports use schemaVersion 2. Invalid registry data is rejected before replacement; demo imports cannot assert a connected Runtime. The existing storage key is retained so a code update on the same origin can load old data.

Localhost ports and the hosted Site have separate browser stores. Updating the project does not transfer records across origins or devices. If browser storage fails, the UI reports it; export before closing the tab.

## Update in WSL2 (WSL2 更新)

Stop the old project server with Ctrl+C, then run:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --check --python python3.11
bash scripts/start-gui.sh
```

Open `http://localhost:8765`. This frontend update adds no dependencies. If the environment check identifies missing prerequisites, run the existing installer before starting. To choose another port:

```bash
bash scripts/start-gui.sh --port 9000
```

Then use `http://localhost:9000`.

## Next implementation boundary (後續實作邊界)

Keep the registry view and replace its browser adapter with an authenticated agent service. Add server-owned config revisions, real Runtime discovery/heartbeat evidence, Skill artifact hashes and task handoff traces. Tie an experiment to an immutable configuration snapshot before real nanobot/GEPA execution. The existing relationship graph can then present configuration alongside measured execution evidence without treating the two as interchangeable.

## Actual model roles (v0.5.0)

A submitted LLM Skill experiment pins the configured role IDs/names, then runs Coordinator, Worker, Reflector, Evaluator and Reviewer in that order. Details show its frozen model, baseline prompt Skill and fixed model protocol separately from browser-local configuration. Nodes retain actual process-status overlays. Configured graph arrows do not schedule this fixed workflow; tool names, memory/steps/temperature in registry records do not alter it. The model runner has no tools and uses fresh messages at temperature 0. See [LLM Skill evolution](llm-skill-evolution.md).
