<!--
  source-discipline.md — Shared discipline for handling source material
  Referenced by: epic-composer, epic-interview, story-decomposer
  version: 1.0.1, owner: John D
  Single source of truth for the rules every skill in the epic-pipeline
  repeats. Skills keep their own interview-/skill-specific rules inline and
  reference this file only for the common ones.
-->

# Source Discipline

Every skill in the epic pipeline handles source material the same way. This
file is the single source for the rules that were previously restated in each
skill's "Non-Negotiable Behavior" block.

## The three information buckets

Classify every piece of information into three buckets and keep them separate
throughout the work:

- **Source Facts** — directly stated in the provided material
- **Inferred Requirements** — reasonable implications from source material
- **Unknowns** — required but not yet established

Never blur the boundaries between these buckets.

## Common non-negotiable rules

Apply these in every skill that handles source material:

- Never hide contradictions — surface each one and name the sections it affects.
- Never invent missing information — mark it Unknown and ask (or mark
  [BLOCKED] if the user cannot answer).
- Never present inferred content as fact — label it Inferred.
- Never declare work ready while major acceptance, scope, or validation gaps
  remain — resolve them or mark [BLOCKED] first.
- Prefer "unknown" over false precision.
- When two or more sources conflict: surface the contradiction explicitly,
  identify the affected sections, ask the user for resolution if the conflict
  changes scope/actors/acceptance/success metrics, and mark the section
  provisional or blocked if unresolved.

## Response-state labeling

A skill that declares a response state (for example a `Ready` / `Needs work` /
`Blocked` verdict) labels it at the **top** of its reply. The states differ per
skill and are listed in its Output section.

## How callers use this file

A skill that says "applies `source-discipline.md`" is invoking the rules above.
A skill may layer additional rules on top (e.g. the interviewer's "do not
rewrite the Epic during interview mode") — those stay inline in the skill and
are not part of this shared doctrine.