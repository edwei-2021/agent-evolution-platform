#!/usr/bin/env bash
# Never trace credential assignments, even when this launcher is run with bash -x.
set +x
set -euo pipefail
LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$LAB_ROOT/.venv/bin/python" ]] || { echo 'Run bash scripts/install-wsl.sh first.' >&2; exit 1; }

# Match the user's existing `source ~/strata-wsl.env` initialization. An empty
# override opts out; an explicitly named missing file is a configuration error.
LAB_STRATA_ENV_FILE="${AEP_STRATA_ENV_FILE-${HOME}/strata-wsl.env}"
if [[ -n "$LAB_STRATA_ENV_FILE" ]]; then
  if [[ -f "$LAB_STRATA_ENV_FILE" && -r "$LAB_STRATA_ENV_FILE" ]]; then
    set -a
    if ! source "$LAB_STRATA_ENV_FILE" >/dev/null 2>&1; then
      printf 'Unable to load Strata environment file: %s\n' "$LAB_STRATA_ENV_FILE" >&2
      exit 1
    fi
    set +a
    set +x
    printf 'Strata environment loaded: %s (values hidden)\n' "$LAB_STRATA_ENV_FILE"
  elif [[ -n "${AEP_STRATA_ENV_FILE+x}" || -e "$LAB_STRATA_ENV_FILE" ]]; then
    printf 'Strata environment file is missing or unreadable: %s\n' "$LAB_STRATA_ENV_FILE" >&2
    exit 1
  else
    printf 'Optional Strata environment file not found: %s; using inherited environment.\n' "$LAB_STRATA_ENV_FILE"
  fi
fi
cd -- "$LAB_ROOT"
mkdir -p -- "$LAB_ROOT/.local/tmp" "$LAB_ROOT/.local/cache"
export TMPDIR="$LAB_ROOT/.local/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export TIKTOKEN_CACHE_DIR="$LAB_ROOT/.local/cache/tiktoken"
export XDG_CACHE_HOME="$LAB_ROOT/.local/cache"
exec "$LAB_ROOT/.venv/bin/python" "$LAB_ROOT/scripts/serve_gui.py" "$@"
