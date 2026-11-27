---
name: epic-interview
description: >
  Ask the smallest set of questions that unblocks an Epic; returns blockers, answers,
  and updated assumptions without drafting the Epic. Trigger phrases: "run interview
  mode", "close gaps on this epic", "clarify these requirements", "what questions do I
  need to answer", "resolve these contradictions". Use when unknowns or conflicting
  sources block scope, acceptance, or story boundaries.
---

# Epic Interview

<!--
  The skill itself. OpenCode reads it here; Claude Code loads it through the
  generated .claude/skills/<name>/SKILL.md pointer.
  contract: templates/_shared/doctrine/skill-execution.md
  version: 4.0.0, owner: John D
  invokes: .agents/doctrine/source-discipline.md
  doctrine: .agents/doctrine/source-discipline.md
-->

Run a short interview that unblocks an Epic. Ask only questions whose answers
change scope, stories, or acceptance. Do not draft or rewrite the Epic.

## Inputs

- Required: the Epic draft, source paths, or problem statement under review.
- Read: `.agents/doctrine/source-discipline.md` and the existing Epic if one exists.
- Do not read: unrelated code or repositories.

## Deterministic Steps

1. **Extract knowns.** Run `rg -n 'AC[0-9]+|Outcome|Scope|Constraint' <epic> 2>/dev/null || true`
   and list the stated problem, actors, outcome, constraints, and existing
   decisions. When an Epic file exists, also run
   `python3 .agents/scripts/validate_artifact.py --kind epic --summary <epic>`;
   record shape failures as gaps, not as facts to invent.
2. **Classify every gap** as one of:
   - **Blocker** — scope, actors, or acceptance cannot be settled.
   - **Shaper** — changes story boundaries, ownership, or sequencing.
   - **Deferrable** — wording, secondary personas, later phases.
3. **Deduplicate.** Drop questions already answered by the sources or the Epic.
4. **Order and cap.** Ask blockers first in one batch; ask at most five questions
   total. For each, state the consequence: what changes if the answer is X or Y.
5. **Record outcomes.** Mark each item resolved, blocked with an owner, or
   deferred. Do not turn a guess into a fact.
6. **Stop at the gate.** When no blocker remains, say the Epic is ready to draft
   and return the updated assumptions.

## LLM Judgment

Use judgment only for:

- deciding whether a gap is genuinely blocking;
- spotting contradictions between sources;
- phrasing a question so the answer is actionable.

Do not invent requirements or answer on the user's behalf.

## Output

```markdown
**Questions**
1. <question> — why: <what changes>

**Blocked**
- <item> — needs <owner / decision>

**Resolved**
- <answer integrated into the assumptions>
```

Use `None` under a heading when it is empty.

## Stop Conditions

- Stop and report if there is no Epic or source material.
- Stop after the question cap; list the remaining gaps as blocked instead of
  asking more.
- If the user does not know, record it as blocked with who can answer.

## Token Budget

- Default: read the Epic, named sources, and `source-discipline.md`.
- Aim for five questions and ≤ 400 words. If a sixth question is truly blocking,
  list it under **Blocked** instead of asking more.
- Do not repeat the Epic or re-list resolved facts.
