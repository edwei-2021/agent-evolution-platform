# GEPA Integration Verification (GEPA 整合驗證)

Release: **v0.7.0**. Actual installed packages: **gepa 0.1.4** and **nanobot-ai 0.3.5**, Python 3.12, Node 24. Model requests use a loopback HTTP fixture; the optimizer and agent SDK are real. No user Windows Ollama/GPU requests were sent.

## Coverage (測試範圍)

- Golden reference repairs for all 50 Full tasks pass their trusted visible/final cases. Smoke/Full counts and disjoint operation-family assignment are checked.
- Real GEPA reflective mutation invokes real nanobot rollouts, selects by validation and independently evaluates frozen baseline/selected Skills.
- Fragmented SSE tool arguments and Skill proposal text survive local/global evidence reconstruction and replay.
- Final task IDs never enter search; reflection contains only training trajectories. Final rollouts start after persisted selection.
- Completed verified improvement supports explicit approval, immutable version persistence and rollback. Duplicate approval and stale revisions are rejected.
- A perfect seed creates no improvement release; a held-out regression blocks approval despite validation improvement.
- A corrupted final score after review fails approval's independent evidence replay.
- Provider HTTP failure sends one request, stops the workflow and releases the provider slot.
- Per-task iteration and global call limits refuse additional requests. Proposal schema errors stop without retry or final-data execution, including GEPA's internally caught proposal-error behavior.
- Cancellation and a silent-response call deadline stop actual SDK processes and finalize global evidence. Warmup cannot overlap the active optimizer.
- A real JavaScript RuntimeClient dispatches through the Python HTTP API, polls actual execution and validates the completed GEPA result.
- Frontend validation rejects fabricated scores/eligibility/budgets/versions. Stale polling and provider/SDK activity gate controls. Uncertain submissions retain their frozen body/ID without automatic retry; definitive rejection permits correction.
- Real application handlers reach GEPA navigation and Start with saved provider/Skill revisions. Existing settings/save, warmup, logs and repair behavior remain under regression coverage.

## Reproduce (重現方式)

```bash
npm test
TIKTOKEN_CACHE_DIR="$PWD/.local/cache/tiktoken" .venv-nanobot/bin/python -m unittest discover -s tests -p '*_test.py'
```

**86 JavaScript and 103 Python tests passed (189 total).** The complete Python suite ran in the actual pinned SDK environment with no skipped tests. Final focused checks cover the last descriptive/observability changes. Installed dependencies passed `pip check`; their `Requires-Python` metadata permits Python 3.11. SDK-only tests intentionally skip when the optional packages are absent; release validation runs them in the actual pinned SDK environment.

## Limits (驗證限制)

The controlled model fixture verifies integration and evidence handling, not qwen3-coder quality. The user's reported v0.6.0 repair pass establishes their earlier local runner result; v0.7.0 still needs their local Smoke run. The managed environment has no supported browser-control skill, so browser-engine visual QA was unavailable; no substitute browser was installed. Runtime execution was Python 3.12; package metadata compatibility with WSL Python 3.11 is checked separately, not a WSL execution claim. Full dataset reference cases and split contracts are checked; end-to-end optimizer cases use Smoke. The hosted publication remains a private static frontend for the local backend.
