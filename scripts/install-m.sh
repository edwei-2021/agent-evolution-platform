#!/usr/bin/env bash
set -euo pipefail
M_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$M_ROOT"
mkdir -p .local/tmp .local/cache/uv
export TMPDIR="$M_ROOT/.local/tmp" UV_CACHE_DIR="$M_ROOT/.local/cache/uv"
export UV_PROJECT_ENVIRONMENT="$M_ROOT/.venv-m"
command -v uv >/dev/null || { echo 'DBG-M-007: install uv from https://docs.astral.sh/uv/getting-started/installation/ then retry.' >&2; exit 1; }
[[ ! -L .venv-m ]] || { echo 'DBG-M-007: .venv-m symlink is forbidden.' >&2; exit 1; }
uv sync --locked
.venv-m/bin/python scripts/generate_m_contracts.py --check
echo 'M dependencies ready. No Ollama requests sent.'
