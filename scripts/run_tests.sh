#!/usr/bin/env bash
# 仓库根目录一键 `uv sync` + pytest（POSIX；Windows 请用 run_tests.ps1）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

uv sync

if [[ $# -eq 0 ]]; then
  set -- tests/
fi
exec uv run pytest "$@"
