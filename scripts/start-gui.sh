#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$LAB_ROOT/.venv/bin/python" ]] || { echo 'Run bash scripts/install-wsl.sh first.' >&2; exit 1; }
exec "$LAB_ROOT/.venv/bin/python" "$LAB_ROOT/scripts/serve_gui.py" "$@"
