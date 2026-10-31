---
read_when: "Writing a README, ADR, API reference, or agent-facing docs (AGENTS.md included)"
---

# Documentation: Run It, Then Explain It

Docs answer three questions in order: what is this, how do I run it, where is
the detail.

## MUST

- The README opens with a one-paragraph purpose, then a quickstart that works
  on a clean checkout.
- Install, test, lint, and run commands in the docs match the current tooling.
  When you change a command, update the docs in the same PR.
- Public contracts (APIs, tools, CLI flags, file formats) have one
  authoritative reference with types, defaults, and error codes.
- `AGENTS.md` loads in every session, so every line costs every session. It
  holds what doesn't change per issue: purpose, architecture, commands, rule
  index, invariants. It holds **no status**: no open/active/done issue lists,
  no per-feature history. Query the tracker and `git log` for status.
- A rule cites at most one issue or ADR for why it exists.

## SHOULD

- An ADR (`docs/adr/NNNN-title.md`) for decisions with real trade-offs.
- One realistic example over several fragments.
- A "gotchas" section for non-obvious behaviour.
- Link checks in CI.

## ANTI-PATTERNS

- Two pages describing the same contract differently.
- Docs that restate the code instead of the contract.
- Undated "coming soon" sections.
