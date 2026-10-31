#!/usr/bin/env bash
# Shared by the post-commit and post-merge hooks (issue #174). Refreshes the
# graphify graph STRUCTURE when the latest commit/merge touched MCP source.
#
# Arg 1 is the invoking mode ("post-commit" | "post-merge", default post-commit).
#
# AST-only + LLM-free (~1-2s); output (graphify-out/) is gitignored, so this
# creates no commit churn. Re-clustering resets community labels to placeholders
# — run `scripts/graphify.sh label .` to refresh names. See .claude/rules/graphify.md.
#
# Best-effort: never fails a commit. Self-contained so it works whether git
# invokes it as post-commit, post-merge, or directly.
set -uo pipefail

mode="${1:-post-commit}"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$ROOT" || exit 0

# Only act when graphify is actually set up in this checkout.
[ -x scripts/graphify.sh ] || exit 0
[ -f graphify-out/.graphify_python ] || exit 0

# Determine which files moved. A fast-forward pull integrates several commits at
# once and the *tip* may be irrelevant, so on post-merge diff the whole merged
# range (ORIG_HEAD..HEAD, which merge/pull set). For post-commit — or if ORIG_HEAD
# is absent — inspect just the new commit.
if [ "$mode" = "post-merge" ] && git rev-parse --verify --quiet ORIG_HEAD >/dev/null; then
    changed="$(git diff --name-only ORIG_HEAD HEAD 2>/dev/null || true)"
else
    changed="$(git diff-tree --root --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
fi
printf '%s\n' "$changed" | grep -qE '^(mcp_server/.*\.py|godot/addons/godot_mcp/.*\.gd)$' || exit 0

# Structure-only refresh; tolerate any failure so git is never blocked.
scripts/graphify.sh update . >/dev/null 2>&1 || true
exit 0
