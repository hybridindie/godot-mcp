---
description: Open or update a PR (GitHub or Gitea), watch CI and the automated review, address the review, and merge once green if the repo's merge policy allows
---

Read and follow the ship-pr skill:

`.agents/skills/ship-pr/SKILL.md` (Claude Code reaches it through the
`.claude/skills/ship-pr` pointer; OpenCode reads it directly).

Arguments: `$ARGUMENTS`

- empty — use the pull request for the current branch
- a PR number or URL — target that PR
- `--no-merge` — watch and address threads, but don't merge (default: merge
  once CI is green and every finding is addressed, unless `merge_policy` in
  `.claude/harness.json` says `never` or the PR touches an irreversible path,
  in which case it stops at "ready for a person")
