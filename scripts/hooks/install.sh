#!/usr/bin/env bash
# Activate the tracked graphify git hooks for this checkout (issue #174).
# core.hooksPath is a local, per-clone setting — run this once after cloning.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x scripts/hooks/post-commit scripts/hooks/post-merge scripts/hooks/_graphify_refresh.sh
git config core.hooksPath scripts/hooks
echo "core.hooksPath -> scripts/hooks (graphify post-commit/post-merge active)"
