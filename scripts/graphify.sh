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
#    falling back to python3 on PATH. Read it into an argv array so a pin like
#    "/usr/bin/env python3" (interpreter + arg) execs correctly — a single quoted
#    "$PYTHON" would be treated as one command name and fail.
PIN="$ROOT/graphify-out/.graphify_python"
py_cmd=(python3)
if [ -f "$PIN" ]; then
    read -r -a _pinned < "$PIN" || true
    if [ "${#_pinned[@]}" -gt 0 ] && "${_pinned[@]}" -c "import graphify" 2>/dev/null; then
        py_cmd=("${_pinned[@]}")
    fi
fi

exec "${py_cmd[@]}" -m graphify "$@"
