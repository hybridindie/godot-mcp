---
name: epic-acceptance-linter
description: >
  Review acceptance criteria for observability, testability, specificity, and coverage;
  suggests concrete rewrites and an optional verdict. Trigger phrases: "lint these
  acceptance criteria", "review the AC", "check if my criteria are testable", "validate
  acceptance criteria", "strengthen the criteria on this epic". Use when criteria have
  been drafted and need a quality pass before decomposition or review.
---

# Epic Acceptance Linter

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 4.1.0, owner: John D
  doctrine: .agents/doctrine/acceptance-criteria-rules.md
-->

Review the acceptance criteria of an Epic or story. Report concrete problems and
replacements; do not rewrite the whole document.

## Inputs

- Required: the Epic or story body, or the criteria block.
- Read: `.agents/doctrine/acceptance-criteria-rules.md`.
- Do not read: implementation code unless a criterion names a contract that
  cannot be judged without it.

## Deterministic Steps

1. **Extract criteria.** Run
   `python3 .agents/scripts/validate_artifact.py --kind acceptance <artifact>`;
   use its `ACn` labels and text. Stop if it reports no criteria.
2. **Apply the six rules** in `.agents/doctrine/acceptance-criteria-rules.md`
   to each criterion (rule 6, coverage, applies to the set).
3. **Classify each finding:** `Blocking`, `Improve`, or `Optional`.
4. **Write one replacement** per finding. Do not add requirements the sources do
   not support.
5. **Check coverage.** Name any Epic outcome or edge case with no criterion.
6. **Stop.** Return the report; do not edit the source document unless the caller
   explicitly asks for the edit.

## LLM Judgment

Use judgment only for:

- whether a criterion is semantically observable and outcome-focused;
- whether an edge case is material to this Epic;
- the wording of a replacement criterion.

Do not turn every criterion into Given/When/Then, and do not lint implementation
detail.

## Output

```markdown
## Acceptance Criteria Review

| AC | Verdict | Problem | Replacement |
|----|---------|---------|-------------|
| AC1 | Blocking/Improve/Optional | <why> | <concrete text> |

**Coverage gaps**
- <outcome or edge case with no criterion>

**Verdict:** Ready | Needs work | Blocked
**Top 3 changes**
1. …
```

## Stop Conditions

- Stop and ask if there are no acceptance criteria.
- Stop if the source is not an Epic or story; report the wrong input.
- Do not invent requirements or silently change scope.

## Token Budget

- Default: read the criteria, the Epic/story around them, and the doctrine file.
  Read a referenced contract only when a criterion cannot be judged without it.
- Target ≤ 700 words; list criteria that need attention. If there are more than
  10 findings, group the lowest-severity ones.
- Do not restate good criteria or the full source.
