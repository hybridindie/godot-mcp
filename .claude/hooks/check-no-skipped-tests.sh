#!/usr/bin/env bash
# Suite-health gate (.claude/rules/testing.md, enforcement.md): zero unconditional
# skips. No @pytest.mark.skip, no xfail, no bare pytest.skip(). Conditional skipif on a
# genuine environmental precondition is allowed.
#
# Exits non-zero (and prints offenders) if a forbidden skip is found under tests/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TESTS_DIR="$ROOT/tests"

[ -d "$TESTS_DIR" ] || { echo "no tests/ directory yet — nothing to scan"; exit 0; }

# Patterns that are always forbidden. skipif (conditional) is intentionally excluded.
PATTERN='@pytest\.mark\.skip\b|@pytest\.mark\.xfail|pytest\.xfail\(|pytest\.skip\('

if matches="$(grep -rnE "$PATTERN" "$TESTS_DIR" --include='*.py')"; then
  echo "Forbidden test skip(s) found — fix the code or delete the test:" >&2
  echo "$matches" >&2
  exit 1
fi

echo "zero-skip scan: clean"
