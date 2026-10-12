#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$LAB_ROOT/.venv/bin/python" ]] || { echo 'Run bash scripts/install-wsl.sh first.' >&2; exit 1; }
cd -- "$LAB_ROOT"
mkdir -p -- "$LAB_ROOT/.local/tmp" "$LAB_ROOT/.local/cache"
export TMPDIR="$LAB_ROOT/.local/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export TIKTOKEN_CACHE_DIR="$LAB_ROOT/.local/cache/tiktoken"
export XDG_CACHE_HOME="$LAB_ROOT/.local/cache"
exec "$LAB_ROOT/.venv/bin/python" "$LAB_ROOT/scripts/serve_gui.py" "$@"
