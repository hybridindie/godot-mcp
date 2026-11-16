---
name: customize-harness
description: Semantically tailor the installed AI harness to the project domain and the user's workflow conventions. Idempotent.
when_to_use: >
  Run after installing the harness, or whenever the project domain, stack, or
  workflow conventions change. Trigger phrases: "customize the harness",
  "tailor the rules", "apply my workflows", "re-tailor AGENTS.md".
user-invocable: true
---

# Customize Harness

<!--
  contract: .claude/rules/doctrine/skill-execution.md
  version: 2.0.0, owner: John D
-->

Tailor the **installed** harness in place. Rendering owns placeholders; this
skill owns semantic fit and workflow weaving. It never needs the genesis repo.

## Inputs

- Required: `AGENTS.md`, `CLAUDE.md`, `my-workflows.md` (if present).
- Read: `README.md`, `pyproject.toml` / `package.json` description or name.
- Read: `.opencode/opencode.json` — the OpenCode LSP surface.
- Read only the rule/agent/command files whose names appear in `AGENTS.md` or the
  requested change; do not open every rule.
- Do not read: `templates/`, generator source, or unrelated repositories.

## Deterministic Steps

1. **Inventory.** Run
   `python3 .claude/skills/customize-harness/scripts/inventory.py --root .`;
   use its JSON counts, workflow-section status, and `lsp` block.
2. **Read domain facts.** Use `README.md` and the manifest fields; if the domain
   is still unclear, ask one question.
3. **Read workflows.** Open `my-workflows.md`; ignore every section that is still
   a `<placeholder>`.
4. **Fit the LSP setup.** Trust the `lsp` block; do not probe for binaries or
   grep extensions yourself.
   - `detected_servers` are the language servers this project needs.
   - `no_builtin_server` are languages with no OpenCode built-in. Report them as
     a gap; never invent a custom server entry without the user asking.
     A language leaves this list once the config declares a server for its
     extension, so `.gd` is satisfied by the `godot` bridge rather than flagged.
   - `current` is `<no-config>`, `<absent>`, `true`, or an object of enabled and
     disabled servers.

   Apply this decision order:

   - `current` is `<no-config>` or `<absent>` → add `"lsp": true`. Create
     `.opencode/opencode.json` only when the project has no OpenCode config.
   - `current` is `true` → leave it; built-ins activate lazily.
   - `current` is an object → ensure no `disabled` entry covers a server in
     `detected_servers`.

   Then report, without fixing: each `binaries_missing` entry (name the binary to
   install — never install it) and each `auto_install_on_first_use` entry (the
   server downloads itself on first use).
5. **Build the edit plan.** One row per file: current problem, exact change,
   reason. Group as domain fit, coverage, LSP, workflow weaving, trim, or missing
   rule.
6. **Stop for approval.** Show the plan and ask “Apply this plan? Reply yes, or
   adjust.” Do not edit before approval.
7. **Apply in place.** Preserve headings. Keep `CLAUDE.md` thin, keep the
   `AGENTS.md` rule index accurate, and never delete user-authored content without
   confirmation.
8. **Validate.** Run
   `python3 .claude/hooks/check-project-drift.py --quiet`; stop on failure.
9. **Report.** List changed files, removed rules, added rules, the LSP outcome,
   and any skipped workflow sections.

## LLM Judgment

Use judgment only for:

- mapping generic examples to the project's actual domain terms;
- deciding which rules genuinely do not fit;
- weaving filled-in workflow conventions into `AGENTS.md` without copying;
- tailoring LSP beyond the default: a non-standard virtualenv needs an explicit
  `pyright` `pythonPath`, and a project that cannot fetch from npm wants the
  `bash` and `yaml-ls` servers disabled instead of left to auto-install.

Do not invent project facts or change the stack.

## Output

```markdown
## Customize Plan
| File | Change | Reason |
|------|--------|--------|

Apply this plan? Reply yes, or adjust.
```

After approval, report:

```markdown
## Customize Result
Changed: <file list>
Rules removed: <list or none>
Rules added: <list or none>
LSP: <servers active | unchanged | degraded: missing <binary>>
Workflow sections skipped: <list or none>
Validation: PASS | FAIL
```

## Stop Conditions

- Stop if `AGENTS.md` or `CLAUDE.md` is missing; run bootstrap first.
- Stop if the plan is not approved.
- Stop if drift validation fails.
- Never add an `lsp` key to `.claude/settings.json`. Claude Code has no such
  setting and ignores it; diagnostics there come from an attached IDE or an MCP
  bridge, not from config. Say this rather than writing a dead key.
- Never install a language-server binary to satisfy `binaries_missing`; report it
  and let the user install it.
- Do not touch `templates/` or any genesis file.

## Token Budget

- Default: read `AGENTS.md`, `CLAUDE.md`, `my-workflows.md`, and the domain
  manifest.
- The inventory `lsp` block is authoritative. Do not walk the tree or run
  `command -v` yourself to second-guess it.
- Open at most five rule files per pass; never load `.claude/rules/**` wholesale.
  If a sixth rule is needed for a correctness decision, include it and say why.
- Plan and report ≤ 300 words each; use a table when more files change.
