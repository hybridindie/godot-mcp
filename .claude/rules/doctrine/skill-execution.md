# Skill Execution Contract

Skills do mechanical work with scripts and commands, and save the model for
judgment. Repeatability and token cost are part of correctness.

## Sections

Every skill body has these sections, in order:

- `## Inputs` — arguments, files to read, files to skip.
- `## Deterministic Steps` — numbered, with exact commands and paths.
- `## LLM Judgment` — the decisions the model makes; nothing else is left to it.
- `## Output` — the exact shape or template.
- `## Stop Conditions` — when to stop, ask, or escalate.
- `## Token Budget` — read and output targets.

## Rules

- If a step can be a script (discovery, parsing, scaffolding, validation), it
  is one. Run it; don't re-derive its result by reading files.
- Read the named inputs, not the repository. When a named input can't answer
  a correctness question, read the smallest extra file and say why.
- A failed validation stops the skill. Diagnose and fix the cause; never
  bypass the check.
- Budgets are targets. Never truncate a correctness-critical read to meet
  one; split the output instead of padding it.
- When a fact only the user can provide is missing, ask one batch of
  blocking questions and stop. Don't continue on a guess.
