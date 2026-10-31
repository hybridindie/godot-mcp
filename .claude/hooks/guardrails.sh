#!/usr/bin/env bash
# Single entry point for the local and CI guardrails.
#
#   guardrails.sh --staged   pre-commit: staged secret scan + drift
#   guardrails.sh --all      pre-push: full scan + drift + `make check`
#   guardrails.sh --ci       CI: full scan + drift, no local test run
#
# Silent on success. The individual checks own their output so a failure is
# actionable and the hook does not repeat the same message twice.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MODE="${1:---staged}"
case "$MODE" in
  --staged) SECRET_ARGS=(--staged); RUN_MAKE=0 ;;
  --all)    SECRET_ARGS=(--all);    RUN_MAKE=1 ;;
  --ci)     SECRET_ARGS=(--all);    RUN_MAKE=0 ;;
  *) echo "guardrails: unknown mode '$MODE' (use --staged, --all or --ci)" >&2; exit 2 ;;
esac

fail() {
  echo "guardrails: $1" >&2
  exit 1
}

# 1. Credentials in the staged diff, or in the whole working tree.
if [[ -f .claude/hooks/check-secrets.py ]]; then
  python3 .claude/hooks/check-secrets.py "${SECRET_ARGS[@]}" --quiet || fail "secret scan failed"
fi

# 2. No new skips/xfails.
if [[ -f .claude/hooks/check-no-skipped-tests.sh ]]; then
  if ! output=$(bash .claude/hooks/check-no-skipped-tests.sh 2>&1); then
    printf '%s\n' "$output" >&2
    fail "suite-health scan failed"
  fi
fi

# 3. Claude/OpenCode command and agent bodies still match.
if [[ -f .claude/hooks/check-primitive-drift.sh ]]; then
  if ! output=$(bash .claude/hooks/check-primitive-drift.sh 2>&1); then
    printf '%s\n' "$output" >&2
    fail "mirror-body drift"
  fi
fi

# 4. AGENTS.md, rule index, mirrors, versions and hooks describe this tree.
if [[ -f .claude/hooks/check-project-drift.py ]]; then
  python3 .claude/hooks/check-project-drift.py --quiet || fail "project drift"
fi

# 5. Pre-push only: run the project's own aggregate check when it exists.
if (( RUN_MAKE )) && [[ -f Makefile ]] && grep -qE '^check:' Makefile; then
  make check
fi
