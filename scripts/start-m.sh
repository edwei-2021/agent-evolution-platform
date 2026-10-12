#!/usr/bin/env bash
set -euo pipefail
M_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$M_ROOT"
[[ -x .venv-m/bin/python ]] || { echo 'Run bash scripts/install-m.sh first.' >&2; exit 1; }
exec .venv-m/bin/python scripts/serve_m.py "$@"
