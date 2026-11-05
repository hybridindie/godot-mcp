#!/usr/bin/env bash
# Point this clone at the tracked git hooks. `core.hooksPath` is local, so
# every clone runs this once; it is never committed.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ ! -d .githooks ]]; then
  echo "install-git-hooks: .githooks/ is missing; re-run the bootstrap." >&2
  exit 1
fi

current="$(git config --get core.hooksPath || true)"
if [[ -n "$current" && "$current" != ".githooks" && "$FORCE" -ne 1 ]]; then
  echo "install-git-hooks: core.hooksPath is already '$current'." >&2
  echo "Refusing to overwrite it. Re-run with --force to use .githooks." >&2
  exit 1
fi

chmod +x .githooks/pre-commit .githooks/pre-push
git config core.hooksPath .githooks
echo "core.hooksPath -> .githooks"
