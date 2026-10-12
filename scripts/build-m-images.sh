#!/usr/bin/env bash
set -euo pipefail
M_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$M_ROOT"
command -v docker >/dev/null || { echo 'DBG-M-004: enable Docker Desktop WSL integration.' >&2; exit 1; }
docker info >/dev/null
mkdir -p .local/m
# Build tag is only a lookup handle. Execution resolves and uses immutable image ID.
docker build -f infra/m/evaluator.Dockerfile -t aep-evaluator:m .
docker image inspect --format '{{.Id}}' aep-evaluator:m > .local/m/evaluator-image.txt
docker build -f infra/m/control.Dockerfile -t aep-control:m .
