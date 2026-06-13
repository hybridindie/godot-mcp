#!/usr/bin/env bash
# graphify wrapper — ALWAYS run graphify through this so the project .env is
# observed. graphify reads os.environ but never loads .env itself, and shells
# spawned by tooling don't auto-source it; without these vars graphify's
# backend auto-detect returns None and it falls back to the uninstalled default
# model (qwen2.5-coder:7b). See .claude/rules/graphify.md.
#
# Usage:  scripts/graphify.sh <graphify-args...>
#   e.g.  scripts/graphify.sh label . --update
#         scripts/graphify.sh query "How does the bridge work?"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Source the project .env (export every assignment) if present.
if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

# 2. Use the interpreter graphify was installed into (pinned by the skill),
#    falling back to python3 on PATH.
PIN="$ROOT/graphify-out/.graphify_python"
if [ -f "$PIN" ] && "$(cat "$PIN")" -c "import graphify" 2>/dev/null; then
    PYTHON="$(cat "$PIN")"
else
    PYTHON="python3"
fi

exec "$PYTHON" -m graphify "$@"
