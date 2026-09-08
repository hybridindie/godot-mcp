#!/usr/bin/env bash
# graphify wrapper — ALWAYS run graphify through this so the project .env is
# observed. graphify reads os.environ but never loads .env itself, and shells
# spawned by tooling don't auto-source it; without these vars graphify's
# backend auto-detect returns None and it falls back to the uninstalled default
# model (qwen2.5-coder:7b). See .opencode/rules/graphify.md.
#
# Policy: LOCAL OLLAMA ONLY — no cloud models. graphify's detect_backend()
# prefers cloud keys (gemini/kimi/claude/openai/deepseek) over ollama, so a
# cloud key leaked into the ambient environment would silently reroute the
# corpus to a paid endpoint; this wrapper refuses to run in that case unless
# --backend ollama is passed explicitly.
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

# 1b. Local-ollama guard: refuse a cloud key unless ollama is pinned explicitly.
# The keys checked are the ones detect_backend() prefers over ollama.
if [[ "${1:-}" != "query" && "${1:-}" != "explain" ]]; then
    wants_ollama=false
    prev=""
    for arg in "$@"; do
        # Only an explicit --backend ollama (or --backend=ollama) opts into
        # ollama; any other token named "ollama" (e.g. a path) must not.
        if [[ "$prev" == "--backend" ]]; then
            [[ "$arg" == "ollama" ]] && wants_ollama=true
        elif [[ "$arg" == --backend=ollama ]]; then
            wants_ollama=true
        fi
        prev="$arg"
    done
    if ! $wants_ollama; then
        for key_var in GEMINI_API_KEY GOOGLE_API_KEY KIMI_API_KEY ANTHROPIC_API_KEY \
                       OPENAI_API_KEY DEEPSEEK_API_KEY; do
            if [[ -n "${!key_var:-}" ]]; then
                echo "ERROR: $key_var is set in the environment — graphify would" \
                     "route to a CLOUD model (detect_backend prefers cloud keys over" \
                     "ollama). Policy here is local ollama only: unset $key_var (or" \
                     "pass --backend ollama) and retry." >&2
                exit 2
            fi
        done
    fi
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
