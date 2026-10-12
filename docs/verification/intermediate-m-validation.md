# Intermediate M Validation Record

Assessment date: 2026-10-12 (Asia/Taipei). Base application: v0.7.1. This delivery is additive M tooling, not a declaration of full intermediate-phase completion.

## Evidence and actual results

- 31 new M component tests passed. They cover backup/migration, strict schemas, real pinned nanobot subprocess via loopback model, durable queue/fences, immutable events, reconnect replay, dataset leakage, safe feedback, paired regressions, budgets, signed approval/activation/rollback, API auth/correlation and failure support bundles.
- One real Docker acceptance test was not executed in this development container because Docker is absent. The component profile skips it explicitly; acceptance does not accept that skip.
- Legacy release profile: 91 JavaScript tests and 116 Python tests passed with actual nanobot 0.3.5 and GEPA 0.1.4 installed. No SDK tests were skipped. These use loopback fixtures and do not call the user's Windows Ollama.
- Generated Pydantic/TypeScript schemas match their checksum. TypeScript 5.9.3 strict noEmit check passed. TypeScript's newer native executable failed in this restricted container; the dependency is therefore pinned to the tested JavaScript compiler.
- Python F-rule lint and high-confidence source credential-pattern checks are required by the M7 profile. This is not an exhaustive external secret audit.
- Strict acceptance: M1, M2 and M3 pass; M4 is blocked by Docker dependency preflight (exit 78). M5, M6 and M7 are blocked without executing their acceptance commands. Their individual component tests above passed independently.
- Real Windows/GPU inference, Docker isolation/build/Compose health, actual Ubuntu move, CI execution and production cutover are not claimed as verified.

## Failure behavior evidence

The gate tests deliberately return exit 3 and exit 78. They assert failed/blocked states, preservation of input hashes/command/output, credential redaction, remediation text, persisted StepCheck and zero invocation of dependent commands.

Strict acceptance produces .local/m/support/MCHECK-.../report.json plus M1.json..M7.json. Its immutable StepChecks are in .local/m/control.sqlite3. These local bundles are not committed or uploaded automatically. CI uploads only redacted gate support files, not operator token, signing key, prompt traces or runtime DB.

## Remaining scope before Phase M closure

The complete source for the delivered tools and checks is present. Full phase closure additionally requires real Docker/WSL gates, authenticated new-GUI integration, migration of production execution onto the canonical ledger, approved candidate selection provenance, optimizer-internal GEPA search resume and Git manifest reconciliation. See the operator guide's per-step matrix. Local signed release activation does not automatically alter legacy active versions.
