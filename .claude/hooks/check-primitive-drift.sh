#!/bin/bash
set -euo pipefail

# Verify that the generated OpenCode agents/commands match their Claude sources:
# same body, frontmatter differs by design. Works in a rendered project (where
# both harnesses exist) and in the genesis repo.
#
#   .claude/agents/*.md   <-> .opencode/agents/*.md
#   .claude/commands/*.md <-> .opencode/commands/*.md

DRIFT=0

extract_body() {
  awk '/^---$/{if (++count == 2) nextfile} count >= 2' "$1"
}

check_pairs() {
  local cdir=$1 odir=$2 cf of name
  [[ -d $cdir ]] || return 0
  for cf in "$cdir"/*.md; do
    [[ -f $cf ]] || continue
    name=$(basename "$cf")
    of="$odir/$name"
    if [[ ! -f $of ]]; then
      echo "DRIFT: missing OpenCode mirror for $cdir/$name"
      DRIFT=1
      continue
    fi
    if [[ "$(extract_body "$cf")" != "$(extract_body "$of")" ]]; then
      echo "DRIFT: $cdir/$name and $odir/$name differ (body)"
      DRIFT=1
    fi
  done
}

check_pairs .claude/agents .opencode/agents
check_pairs .claude/commands .opencode/commands

if [[ $DRIFT -gt 0 ]]; then
  echo "FAIL: OpenCode mirror drift found."
  exit 1
fi

echo "PASS: OpenCode agents/commands match their Claude sources."
