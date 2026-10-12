#!/usr/bin/env bash
# Install the optional version-pinned runner separately from the stdlib GUI.
set -euo pipefail
LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_PYTHON="$LAB_ROOT/.venv/bin/python"
[[ -x "$LAB_PYTHON" ]] || { echo 'Run bash scripts/install-wsl.sh first.' >&2; exit 1; }
cd -- "$LAB_ROOT"
mkdir -p .local/tmp .local/cache/pip .local/cache/tiktoken
export TMPDIR="$LAB_ROOT/.local/tmp" TMP="$LAB_ROOT/.local/tmp" TEMP="$LAB_ROOT/.local/tmp"
export PIP_CACHE_DIR="$LAB_ROOT/.local/cache/pip" XDG_CACHE_HOME="$LAB_ROOT/.local/cache" TIKTOKEN_CACHE_DIR="$LAB_ROOT/.local/cache/tiktoken"
[[ ! -L "$LAB_ROOT/.venv-nanobot" ]] || { echo 'Use a project-local .venv-nanobot directory; external symlinks are not supported.' >&2; exit 1; }
if [[ ! -d "$LAB_ROOT/.venv-nanobot" ]]; then "$LAB_PYTHON" -m venv --copies "$LAB_ROOT/.venv-nanobot"; fi
[[ -x "$LAB_ROOT/.venv-nanobot/bin/python" ]] || { echo 'Incomplete .venv-nanobot; inspect it before retrying.' >&2; exit 1; }
"$LAB_ROOT/.venv-nanobot/bin/python" -c 'import pathlib,sys; assert sys.version_info >= (3,11); assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(".venv-nanobot").resolve(), "SDK interpreter must belong to this project environment"'
"$LAB_ROOT/.venv-nanobot/bin/python" -m pip install --disable-pip-version-check -r "$LAB_ROOT/requirements-nanobot.txt"
"$LAB_ROOT/.venv-nanobot/bin/python" -c 'from nanobot import Nanobot; import importlib.metadata; assert importlib.metadata.version("nanobot-ai") == "0.3.5"; print("nanobot SDK 0.3.5 imported; no model requests sent.")'

"$LAB_ROOT/.venv-nanobot/bin/python" -c 'import gepa,importlib.metadata; assert importlib.metadata.version("gepa") == "0.1.4"; print("GEPA 0.1.4 imported; no model requests sent.")'
"$LAB_ROOT/.venv-nanobot/bin/python" -c 'import tiktoken; tiktoken.get_encoding("cl100k_base"); print("Tokenizer cache ready; no Ollama requests sent.")'
