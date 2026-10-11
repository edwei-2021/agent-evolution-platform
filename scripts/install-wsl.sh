#!/usr/bin/env bash
# Bootstrap the dependency-free Python installer with the user's interpreter.
set -euo pipefail
LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_PYTHON=""
LAB_ARGS=()
while (($#)); do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo 'ERROR: --python requires an executable path or name.' >&2; exit 2; }
      LAB_PYTHON="$2"; shift 2 ;;
    *) LAB_ARGS+=("$1"); shift ;;
  esac
done
if [[ -z "$LAB_PYTHON" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then LAB_PYTHON=python3.11
  elif command -v python3 >/dev/null 2>&1; then LAB_PYTHON=python3
  else echo 'ERROR: Python 3.11+ is required. Install Python first; then use --python /path/to/python3.11.' >&2; exit 1
  fi
fi
command -v "$LAB_PYTHON" >/dev/null 2>&1 || { echo "ERROR: Python executable not found: $LAB_PYTHON" >&2; exit 1; }
exec "$LAB_PYTHON" "$LAB_ROOT/scripts/setup_wsl.py" "${LAB_ARGS[@]}"
