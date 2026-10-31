#!/usr/bin/env bash
# Activate the tracked git hooks for this checkout: graphify refresh (issue #174)
# and the harness guardrails (pre-commit/pre-push delegate to .githooks/).
# core.hooksPath is a local, per-clone setting — run this once after cloning.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x scripts/hooks/post-commit scripts/hooks/post-merge scripts/hooks/_graphify_refresh.sh \
  scripts/hooks/pre-commit scripts/hooks/pre-push .githooks/pre-commit .githooks/pre-push
git config core.hooksPath scripts/hooks
echo "core.hooksPath -> scripts/hooks (graphify post-commit/post-merge + guardrails pre-commit/pre-push active)"
