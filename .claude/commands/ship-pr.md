---
description: Open or update a PR, watch CI and the PR-agent review, address the review, and merge with --merge when green
---

Read and follow the ship-pr skill:

- Claude Code: `.claude/skills/ship-pr/SKILL.md`
- OpenCode: `.opencode/skills/ship-pr/SKILL.md`

Arguments: `$ARGUMENTS`

- empty — use the pull request for the current branch
- a PR number or URL — target that PR
- `--merge` — allow merging after the gates pass (default: never merge)
