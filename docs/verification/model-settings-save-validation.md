# Model Settings Save Validation (模型設定儲存驗證)

Release: **v0.5.1**. Development runtime: Linux, Python 3.12.14, Node 24.19.0. No additional dependencies were installed.

## Failure and fix (失敗原因與修正)

The v0.5.0 global click listener called `render()` for a form's submit button before the browser's default submit action. Replacing `#main` detached the original form, reset the model field, and prevented the settings POST. The app event regression test reproduced the failure when the old click behavior was restored.

The listener now leaves form submit buttons to their submit handlers and redraws only after recognized demo actions. Ollama save and chat buttons explicitly use `type="submit"`. Draft settings survive busy-state rendering and failed saves. The saved model/revision shown below the form comes from the backend response; inference continues to use persisted settings. Explicit Reload replaces the draft with persisted settings.

## Verification (驗證)

| Check | Evidence |
| --- | --- |
| Mouse Save | Real app listeners preserve the connected form and send the typed model ID in exactly one settings POST. |
| Enter submit | Numeric settings are converted correctly and the saved model remains visible. |
| Navigation and LLM start | Returning to Integrations reads the saved ID; LLM submission pins the updated provider revision. |
| Failed save | Entered model and timeout remain visible, the backend model remains unchanged, and the error replaces any success message. |
| Other submit buttons | Chat, Skill trial and dialog submit buttons do not trigger a click-time redraw. |
| Real Python API | `OllamaUI` saves `qwen3-coder:30b` from an empty model configuration, a fresh UI instance reads it, and `RuntimeClient` completes Smoke through the real HTTP API. All 15 mock model calls use the saved ID. Approval and rollback still pass. |
| Regression | 58 JavaScript and 58 Python tests passed, 116 total. Commands: `npm test` and `python3 -m unittest discover -s tests -p '*_test.py'`. |

The JavaScript app test uses a minimal event/DOM harness, including form detachment on page replacement. It is not a browser-engine test. Backend transport tests use actual loopback HTTP and supervised subprocesses with mock Ollama. The user's Windows Ollama service was not contacted, and Windows browser interaction/model quality were not tested. Existing port 11435, gateway discovery and proxy bypass were retained.

## WSL update (WSL 更新)

Stop the GUI with Ctrl+C, then run:

```bash
cd /mnt/d/nanobot-gepa-mvp
git pull --ff-only
bash scripts/start-gui.sh
```

Refresh `http://localhost:8765/#integrations` with Ctrl+Shift+R and confirm v0.5.1. Enter the exact model ID, click Save, and check **已儲存模型** (saved model). Then open LLM Skills and start Smoke. No repeated Windows/Ollama setup is required.
