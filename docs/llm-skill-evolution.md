# LLM Skill Evolution (LLM 技能演化)

Version 0.5.0 adds actual model execution and one training-based prompt mutation to the existing polling GUI. Engine: `ollama-prompt-reflection-v1`, implemented in this repository. This is a bounded reflection workflow, not a GEPA or nanobot SDK adapter.

## Start with the established endpoint (沿用既有連線)

Stop the previous GUI with Ctrl+C, then update the existing D-drive checkout:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/install-wsl.sh --check --python python3.11
bash scripts/start-gui.sh
```

If the environment check reports missing prerequisites, run `bash scripts/install-wsl.sh --python python3.11` before starting. There are no new third-party Python dependencies. Existing `.local/ollama/settings.json` is retained; do not run the configuration command again just to upgrade.

Open `http://localhost:8765/#integrations`, select and save an exact installed model ID if none is selected. The Windows port remains 11435 by default; the GUI port remains 8765 and is separately configurable. The supplied Windows/WSL metadata evidence is accepted. No startup probe, metadata refresh, firewall change, model pull or diagnostic rerun is required.

Open `http://localhost:8765/#llm`, keep **Smoke** for the first run, and click **Start LLM Skill evolution**. This explicit action submits real inference requests to the saved endpoint. Inspect roles/PIDs/logs in **Execution monitor**. The GUI polls the Python service every two seconds; it does not need synchronized screen sharing or streaming.

## Profiles and budgets (資料分割與預算)

| Profile | Train / Validation / Held-out | Maximum model calls | Purpose |
| --- | --- | --- | --- |
| Smoke (default) | 3 / 2 / 2 | 15 | Verify the real model execution/evidence/review path |
| Full | 20 / 10 / 20 | 101 | Execute the complete handwritten normalization fixture |

Smoke selects fixed, distinct groups from the existing dataset: training includes case/whitespace, full-width Unicode and case-folding examples. Its held-out tasks remain separate. These subsets and their hashes are frozen at submission.

Each profile executes baseline training and validation, one reflection request, candidate training and validation, then baseline and selected-candidate held-out evaluation. Validation ties retain the baseline. When the baseline wins, its held-out results are reused: Smoke uses 13 calls and Full uses 81 calls. The maximum call budget includes reflection and both held-out evaluations. Review and approval send no additional model requests.

The whole-run deadline defaults to **900 seconds**, adjustable from 60 to 7200 in the GUI. It replaces the native-tool workflow's per-stage 120-second deadline for model runs, so cold model loading can use the saved inference timeout. Each call still has its configured socket timeout, bounded by remaining run time. The supervisor terminates the subprocess at the whole-run deadline. `maxOutputTokens = callBudget × saved maxTokens` is the sum of configured per-call output ceilings, not an observed usage total. Raw provider usage, when supplied, is retained separately.

One workflow runs at a time across project-health, rule-skill and LLM-skill tasks. A model workflow also reserves the local provider operation slot; Web manual metadata/chat requests cannot overlap it. Windows Ollama may continue computing an already dispatched request after a client process is cancelled. Cancellation stops future requests and queued roles; it does not claim server-side generation cancellation. No automatic retry occurs, including after an uncertain submission response.

## Five roles and trusted evaluation (角色與可信評測)

| Role | Actual operation |
| --- | --- |
| Coordinator | Freeze baseline, provider settings/endpoint, dataset/code hashes and budgets |
| Worker | Execute baseline Skill with fresh messages for each training/validation task |
| Reflector | Ask the same frozen model for one candidate body using baseline training failures only |
| Evaluator | Use the Worker runner to execute candidate tasks, select strictly on validation improvement, then evaluate held-out tasks |
| Reviewer | Rebuild task scores from raw model responses and verify request contents/order/accounting; no re-inference |

Each role is a supervised Python subprocess. Worker and Reflector are model operations; Coordinator/Reviewer use trusted code, and Evaluator invokes the model runner while owning score computation. These are not five independently installed LLM frameworks. Agent configuration records remain browser-local; a run pins role bindings and uses the server-owned model config. Configured tools, memory, temperature, steps and graph relationships do not change this fixed runner. Agent details display the experiment's frozen model/baseline separately from configuration fields.

The fixed task is `normalize-support-title`. The name and description are immutable; only its instruction body evolves. The model receives the Skill body as system instructions and a JSON input object containing only the task text. It has no tools, shell access or shared conversation memory. Temperature is fixed at 0 for both execution and reflection.

Requests use `/v1/chat/completions`, non-streaming responses and `response_format: {"type":"json_object"}`. Task responses must contain exactly one string field, `output`. Scoring compares that string to the expected output **without stripping whitespace**. Invalid task JSON is a failed task with a recorded format error; HTTP failure, empty visible completion or invalid candidate JSON fails the workflow. Reflection must return exactly one `body` field; changing metadata is rejected.

Reflector sees only baseline training failures. Validation and held-out inputs/outputs are excluded from its request. Validation selects the candidate before any held-out request. Reviewer checks those payloads and temporal ordering, not just reported success counts. No deterministic text transform replaces a model answer.

## Evidence, approval and rollback (證據、核准與回復)

The Web page shows model calls, last request state, candidate/baseline validation scores, instruction diffs, baseline training failures, held-out results, history, versions and export controls. Existing process polling shows actual subprocess status/PIDs/logs. Stale snapshots disable submission and approval. Reading state never triggers inference.

Evidence is saved under `.local/runs/RUN-.../` on D:

- `llm-config.json` and `llm-manifest.json`: frozen run settings, baseline and provenance.
- `llm-calls.json`: actual request messages, raw provider responses/usage, timestamps, duration and failures.
- `llm-baseline-evaluation.json`: baseline task records.
- `llm-search.json` and `llm-candidate.md`: candidate body and lineage.
- `llm-evaluation.json` and `review.json`: independently recomputed scores and evidence hash.
- `llm-progress.json` and role logs: polling state and process output.

API artifact previews are limited to 200,000 characters and expose `truncated` / `totalChars`; complete files remain available in the local run directory. Logs contain task prompts and responses and are excluded from Git.

Approval requires a completed run, a strict validation success-count improvement, no held-out regression, unchanged active baseline and matching frozen config/raw-evidence hash. The backend recomputes evidence before approval and rejects altered records. No automatic release occurs. Approval atomically creates and activates an immutable `LSV-...` / `L1...` prompt version in SQLite. An old approved version can be reactivated without deleting evidence; unfinished runs retain their originally frozen baseline. Export downloads the selected version's `SKILL.md`.

Prompt versions and state are separate from `SKV-...` / `S0...` rule versions. A model release affects future LLM experiments; it does not activate a Python rule policy or install a Skill into an external framework. Registry/demo JSON backups do not contain server-owned model state; back up `.local/` with the service stopped.

## Limits and next work (限制與後續工作)

Smoke demonstrates workflow viability; two validation/held-out examples cannot establish general improvement. Full is still a small handwritten fixture. Repeated experiments on the same held-out tasks are regression checks, not an independent generalization study. Temperature 0 does not guarantee identical inference outputs across reruns; approval verifies this run's recorded evidence rather than regenerating answers.

The run pins model ID and provider config, not immutable model weights/digest or the Ollama server build. A mutable model tag can change outside this process. Scores therefore apply to the observed run/config, not an immutable model artifact. The same model is used for Worker/Reflector; per-role model selection, external memory and tool execution are later extensions. The static hosted Site cannot run this backend or reach the user's WSL automatically; use the local GUI.

Next: integrate the verified nanobot SDK runner and a real GEPA adapter against these trace/evaluator contracts; add model identity/version capture without requiring redundant connection diagnostics, independent datasets and authenticated remote access. Preserve the existing approval, revision, call/deadline and cancellation boundaries.

Ollama endpoint contract: [official OpenAI compatibility documentation](https://docs.ollama.com/api/openai-compatibility).
