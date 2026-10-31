# My Workflows

> Personal conventions that apply to every repo. `CLAUDE.md` imports this
> file; `customize-harness` weaves the relevant parts into `AGENTS.md`.
> Edit the copy in genesis to change the default for future installs; edit
> this copy to change it for this repo only.
>
> Test discipline lives in `.claude/rules/testing.md` and the delivery flow in
> `.claude/rules/workflow.md`. Machine facts (shell, `rg`/`fd`, direnv) live in
> the user-level `AGENTS.md`. Don't restate either here.

## Version control

- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`,
  `test:`); imperative subject ≤ 72 chars; the body says why.
- Short-lived branches off `main`, named after the issue
  (`<type>/<issue>-<slug>`). Squash-merge, then delete the branch.
- Force-push only with `--force-with-lease`.
- Read the full diff before committing. Never commit generated output, `.env`,
  or credentials.

## Code review

- Review handling lives in `.claude/rules/workflow.md` (step 6).
- No machine-specific paths in code, logs, or commits.

## Tooling

- Python: `uv` only (`uv add`, `uv run`, `uv sync --locked`); never `pip
  install` into the project. ruff for lint and format; mypy or pyright,
  whichever the repo already uses.
- Don't assume a daemon (Docker, Postgres, Ollama) is running unless the
  README says how to start it.
- Use sandbox or paper credentials in development; never production keys.

## Agent behaviour

- Stay inside the files the issue says you own; anything else becomes a note
  or a new issue.
- If a subsystem is planned but not implemented, ask before building it.
- Comments explain *why*, not *what*.
