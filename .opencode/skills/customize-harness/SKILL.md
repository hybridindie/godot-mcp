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
- Read only the rule/agent/command files whose names appear in `AGENTS.md` or the
  requested change; do not open every rule.
- Do not read: `templates/`, generator source, or unrelated repositories.

## Deterministic Steps

1. **Inventory.** Run
   `python3 .claude/skills/customize-harness/scripts/inventory.py --root .`;
   use its JSON counts and workflow-section status.
2. **Read domain facts.** Use `README.md` and the manifest fields; if the domain
   is still unclear, ask one question.
3. **Read workflows.** Open `my-workflows.md`; ignore every section that is still
   a `<placeholder>`.
4. **Build the edit plan.** One row per file: current problem, exact change,
   reason. Group as domain fit, coverage, workflow weaving, trim, or missing rule.
5. **Stop for approval.** Show the plan and ask “Apply this plan? Reply yes, or
   adjust.” Do not edit before approval.
6. **Apply in place.** Preserve headings. Keep `CLAUDE.md` thin, keep the
   `AGENTS.md` rule index accurate, and never delete user-authored content without
   confirmation.
7. **Validate.** Run
   `python3 .claude/hooks/check-project-drift.py --quiet`; stop on failure.
8. **Report.** List changed files, removed rules, added rules, and any skipped
   workflow sections.

## LLM Judgment

Use judgment only for:

- mapping generic examples to the project's actual domain terms;
- deciding which rules genuinely do not fit;
- weaving filled-in workflow conventions into `AGENTS.md` without copying.

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
Workflow sections skipped: <list or none>
Validation: PASS | FAIL
```

## Stop Conditions

- Stop if `AGENTS.md` or `CLAUDE.md` is missing; run bootstrap first.
- Stop if the plan is not approved.
- Stop if drift validation fails.
- Do not touch `templates/` or any genesis file.

## Token Budget

- Default: read `AGENTS.md`, `CLAUDE.md`, `my-workflows.md`, and the domain
  manifest.
- Open at most five rule files per pass; never load `.claude/rules/**` wholesale.
  If a sixth rule is needed for a correctness decision, include it and say why.
- Plan and report ≤ 300 words each; use a table when more files change.
