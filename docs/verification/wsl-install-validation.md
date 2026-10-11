# Installation verification — 2026-10-11

Target: WSL2 / Ubuntu 24.04 / an existing Python 3.11 interpreter, x86_64 or aarch64.

Available validation environment: Ubuntu 24.04.3 container, Linux kernel 6.18.44, Python 3.12.14 and Linux Node 24.19.0. This container is not the user's WSL host and has no Python 3.11 executable. Tools supplied by the execution image are not represented as installed Ubuntu APT packages; a read-only doctor correctly reports missing APT package records and absent project `.venv` on the first check.

Verified:

- Bash entry scripts pass `bash -n`.
- Python installer/server compile under Python 3.12; only Python 3.11+ standard-library APIs are used.
- 14 JavaScript domain/persistence tests pass.
- 13 Python tests pass: WSL1/WSL2 classification, architecture mapping, package selection, APT argv, Linux Node acceptance, SHA-256 rejection, failed-download cleanup, virtual environment reuse/mismatch, venv package availability, read-only checking and live HTTP serving/path isolation.
- Actual creation of a project `.venv` without pip and launch through `start-gui.sh` are smoke-tested locally; the GUI entry and module assets return HTTP 200.

Not executed: a real WSL2 host, Python 3.11, ARM64 binaries, Windows-to-WSL localhost forwarding, sudo/APT mutations, external Node artifact downloads, or browser visual QA. Package/download behavior is covered with offline tests, not reported as a completed installation on the user's computer. The WSL installer runs its own environment check and both test suites before recording installation success on the target host.
