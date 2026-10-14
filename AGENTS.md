# Instructions for AI maintainers

Before changing stage M acceptance, runtime discovery, workflow deadlines, or test supervision, read `docs/ai-maintenance-lessons.md` and the relevant section of `docs/intermediate-m.md`.

- Start from the first failed leaf case and its exact source/report identity. Separate observed evidence from hypotheses.
- Audit later unexecuted cases for the same dependency, cold-cache, deadline, and cancellation risks before publishing a fix.
- Keep state reads independent of optional SDK imports and model work. Readiness observations never authorize dispatch; pinned checks belong in configuration freezing.
- Derive enforcement limits from serial work, including independent verification and cleanup. Human duration estimates do not extend hard deadlines.
- Prove slow/cold/expired-cache behavior and real failure paths locally. A fast local pass does not establish a WSL pass.
- Use exact case selection or the scoped M7 continuation runner when diagnosing a failed tail. Never silently promote historical passed evidence to acceptance of changed source.
- Preserve per-case evidence, failure logs, source hashes, and bounded unattended cleanup. Unknown case IDs and empty selections must fail.
- Respect existing publication authorization. Do not ask the user to repeat long upstream checks just to discover independent downstream defects.

- For every affected integration case, expand its subprocess/test-discovery graph to leaf commands. Record the expanded module list and every enclosing execution and cleanup deadline; checking only the top-level test file is insufficient.
- A wildcard test selector requires an audited manifest. Scope growth must update its frozen budget and regression proof.
- Before reporting a deadline repair complete, exercise a controlled child beyond the former child AND parent limits, verify process-group cleanup, and confirm temporary run logs survive into the exported support ZIP.
