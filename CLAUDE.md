# Claude Code

@AGENTS.md
@my-workflows.md

## Claude Code specifics

- **Project context lives in `AGENTS.md`** (imported above). Keep Claude-only
  details here; do not duplicate the project overview, stack or rule index.
- **Rules:** `.claude/rules/**` is discovered natively. Files with `paths:`
  frontmatter are scoped to matching files and load lazily; files without
  `paths:` load at launch. The `AGENTS.md` rule index still says which rule is
  relevant to a task.
- **Hooks:** `.claude/hooks/` holds the skip, secret and drift gates; the tracked
  `.githooks/` run the fast ones locally. Use `/preflight` before pushing. Never
  bypass hooks with `--no-verify`.
- **Agents:** `.claude/agents/*.md` are read-only routers; delegate design
  questions to them instead of duplicating their guidance.
- **Skills and commands:** `.claude/skills/` and `.claude/commands/`; names are
  listed in `AGENTS.md` under Harness Map.
- **Customization:** `/harness-eval` then `/customize-harness`; both edit
  `AGENTS.md` (canonical) and leave this file thin.
