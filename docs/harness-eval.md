# Harness Evaluation

Run after the harness is rendered into a project (`/harness-eval`). Rendering
is deterministic: it picks stacks from manifests and fills placeholders. This
pass reads the actual code, checks each rule fits, trims what doesn't, and
suggests what's missing. Propose first; edit only after the user confirms.

## Inputs

- `.claude/harness.json` — the rendered `stacks`, `packs`, and `paths`.
- `AGENTS.md` (canonical context and rule index), `.claude/rules/**`,
  `.claude/agents/`, `.claude/commands/`, `my-workflows.md`.
- The project itself: manifests (`pyproject.toml`, `package.json`,
  `project.godot`, `Cargo.toml`), lockfiles, CI config, entry points, a few
  representative source and test files.

## 1. Verify the stacks

Read the code, not just the manifest. For each stack in `harness.json`,
confirm it is really used; then look for stacks the code uses but the harness
lacks.

| Stack | Evidence it applies |
|---|---|
| `python` | `pyproject.toml` / `requirements.txt` with real dependencies |
| `mcp` | `mcp` / `fastmcp` dependency and a server module |
| `agent` | LangGraph/LangChain/MLflow, or LLM SDK calls plus evals |
| `fastapi` | FastAPI app and routers |
| `frontend` | React/Next/Vue/Svelte app |
| `godot` | `project.godot` |
| `godot-addon` | the project's own `addons/<name>/plugin.cfg` |
| `rust` | `Cargo.toml` |

Packs: suggest `production` if the project deploys a long-running service
(Docker/compose/k8s) and `acd` only if the user wants the stricter ACD session
discipline.

Stack and pack changes go through a re-render, because the drift gate checks
that the rules on disk match `harness.json`:

```bash
bash <genesis>/templates/scripts/bootstrap.sh --output-dir . --add-stacks rust
bash <genesis>/templates/scripts/bootstrap.sh --output-dir . --remove-stacks frontend
bash <genesis>/templates/scripts/bootstrap.sh --output-dir . --packs production
```

(The `bootstrap-harness` skill fetches genesis and runs this for you.)
Re-rendering keeps files you have edited since the last render (it lists
them) and adds the new stack's rules and index rows; update the AGENTS.md
Stack and Key Commands sections by hand if AGENTS.md was one of the kept
files.

## 2. Check each rule fits

For every rule in the index, check it against the code:

- Does it name a framework, tool, or path the project doesn't use?
- Do its `paths:` globs match real files?
- Does a MUST contradict how the project deliberately works (and is that a
  defect to fix or a rule to change)?

| Rule | Fits? | Issue (be specific: name the file/import) | Action |
|---|---|---|---|

Actions: **keep**, **trim** (remove the sections that don't apply), **edit**
(adjust to the project's real tool, e.g. Jest instead of Vitest), or **remove**
(the rule can't apply; delete it and its index row).

## 3. Suggest missing rules

Only from evidence in the code. Look for: background jobs and queues, search /
embeddings, file uploads, multi-tenancy / RLS, real-time (WebSocket, SSE,
LISTEN/NOTIFY), API versioning, feature flags, caching, external API clients
with rate limits, data migrations, and domain invariants the code enforces but
no rule states. For each: one line on why, where it belongs (existing rule or
new file), and a 2–3 bullet stub. Don't create files until the user picks.

## 4. Report

```
## Harness Evaluation

### Stacks
harness.json: <stacks/packs>  Code: <what the code shows>  Change: <none | add/remove …>

### Rule fit
<table from step 2, non-"keep" rows only>

### Missing rules
<suggestions>

### Next
1. Apply stack/pack changes (re-render)   2. Apply rule edits   3. Run /customize-harness
```

## Editing conventions

- Rule files keep this shape: frontmatter with a required `read_when:` (the
  rule index is built from it) and optional `paths:`, then `## MUST`,
  `## SHOULD`, `## ANTI-PATTERNS` as needed. MUST is for rules whose breach is
  a defect; preferences are SHOULD.
- One home per rule. If a rule already exists in another file, link to it
  (`see testing.md`) instead of restating it.
- When you add, remove, or rename a rule, update the `AGENTS.md` rule index in
  the same change; `python3 .claude/hooks/check-project-drift.py` must pass.
- Keep `CLAUDE.md` thin (imports plus Claude-only notes). Agent and command
  edits go in `.claude/`; the `.opencode/` mirrors must match (same body).
- Edit the rendered project only; never the genesis repo from here.
