#!/usr/bin/env bash
set -euo pipefail
kit_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null; then
  echo 'Install dependencies: sudo apt-get update && sudo apt-get install -y python3 curl iproute2' >&2
  exit 1
fi
exec python3 "$kit_script_dir/check-ollama.py" "$@"
