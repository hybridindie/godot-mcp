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
  version: 2.1.0, owner: John D
-->

Tailor the **installed** harness in place. Rendering owns placeholders; this
skill owns semantic fit and workflow weaving. It never needs the genesis repo.

## Inputs

- Required: `AGENTS.md`, `CLAUDE.md`, `my-workflows.md` (if present).
- Read: `README.md`, `pyproject.toml` / `package.json` description or name.
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
4. **Report language-server fit.** OpenCode v2 keeps the `lsp` key but runs no
   servers, so don't add or change `lsp` in `opencode.json` (root or
   `.opencode/`). Trust the inventory's `lsp` block; do not probe yourself.
   - `detected_servers` are the languages a Claude Code code-intelligence plugin
     would help with; list them as a suggestion, never install one.
   - `current` is `<no-config>`, `<absent>`, `<invalid>` (an OpenCode config
     that doesn't parse — report it as a defect) or the configured entries.
5. **Build the edit plan.** One row per file: current problem, exact change,
   reason. Group as domain fit, coverage, workflow weaving, trim, or missing
   rule.
6. **Stop for approval.** Show the plan and ask “Apply this plan? Reply yes, or
   adjust.” Do not edit before approval.
7. **Apply in place.** Preserve headings. Keep `CLAUDE.md` thin, keep the
   `AGENTS.md` rule index accurate, and never delete user-authored content without
   confirmation.
8. **Validate.** Run
   `python3 .claude/hooks/check-project-drift.py --quiet`; stop on failure.
9. **Report.** List changed files, removed rules, added rules, the LSP note,
   and any skipped workflow sections.

## LLM Judgment

Use judgment only for:

- mapping generic examples to the project's actual domain terms;
- deciding which rules genuinely do not fit;
- weaving filled-in workflow conventions into `AGENTS.md` without copying;

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
LSP: <suggested code-intelligence plugins | none>
Workflow sections skipped: <list or none>
Validation: PASS | FAIL
```

## Stop Conditions

- Stop if `AGENTS.md` or `CLAUDE.md` is missing; run bootstrap first.
- Stop if the plan is not approved.
- Stop if drift validation fails.
- Never add an `lsp` key to `.claude/settings.json` or `opencode.json`; neither
  harness runs servers from it. Claude Code gets them from plugins or `/ide`.
- Never install a language server or plugin; suggest it and let the user act.
- Do not touch `templates/` or any genesis file.

## Token Budget

- Default: read `AGENTS.md`, `CLAUDE.md`, `my-workflows.md`, and the domain
  manifest.
- The inventory `lsp` block is authoritative. Do not walk the tree or run
  `command -v` yourself to second-guess it.
- Open at most five rule files per pass; never load `.claude/rules/**` wholesale.
  If a sixth rule is needed for a correctness decision, include it and say why.
- Plan and report ≤ 300 words each; use a table when more files change.
