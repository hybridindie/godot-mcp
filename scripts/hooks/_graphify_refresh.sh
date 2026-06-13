#!/usr/bin/env bash
# Shared by the post-commit and post-merge hooks (issue #174). Refreshes the
# graphify graph STRUCTURE when the latest commit/merge touched MCP source.
#
# AST-only + LLM-free (~1-2s); output (graphify-out/) is gitignored, so this
# creates no commit churn. Re-clustering resets community labels to placeholders
# — run `scripts/graphify.sh label .` to refresh names. See .claude/rules/graphify.md.
#
# Best-effort: never fails a commit. Self-contained so it works whether git
# invokes it as post-commit, post-merge, or directly.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" || exit 0

# Only act when graphify is actually set up in this checkout.
[ -x scripts/graphify.sh ] || exit 0
[ -f graphify-out/.graphify_python ] || exit 0

# Files changed by the most recent commit (HEAD). For a merge HEAD is the merge
# commit; that's fine — we only need to know whether graph-relevant source moved.
changed="$(git diff-tree --root --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
printf '%s\n' "$changed" | grep -qE '^(mcp_server/.*\.py|godot/addons/godot_mcp/.*\.gd)$' || exit 0

# Structure-only refresh; tolerate any failure so git is never blocked.
scripts/graphify.sh update . >/dev/null 2>&1 || true
exit 0
