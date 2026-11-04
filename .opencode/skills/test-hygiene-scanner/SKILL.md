---
name: test-hygiene-scanner
description: Triage hardcoded dates, AsyncMock misuse, cross-tier truncates, envelope assertions, and singleton leaks in tests.
when_to_use: >
  Run when tests are flaky, misleading, or before trusting a green suite. Trigger
  phrases: "scan test hygiene", "find flaky tests", "audit mocks", "check test
  dates".
user-invocable: true
disable-model-invocation: true
---

# Test Hygiene Scanner

<!--
  contract: .claude/rules/doctrine/skill-execution.md
  version: 2.0.0, owner: John D
-->

Run a fixed set of searches over test files, then use judgment only to triage
the hits. The searches are deterministic; do not invent categories or scan
production code.

## Inputs

- Required: the test roots (`tests godot/tests`).
- Read: only the file:line hits and enough surrounding lines to classify them.
- Do not read: production source, migrations, or unrelated repositories.

## Deterministic Steps

1. **Scan once.**
   ```bash
   python3 .claude/skills/test-hygiene-scanner/scripts/scan.py \
     tests godot/tests
   ```
   The script owns the categories and regexes; do not run alternate searches.
2. **Triage every hit.** For each, open only the surrounding lines and assign:
   - `ERROR` — definitely wrong for this project.
   - `WARNING` — may cause flakes or false confidence.
   - `CLEAN` — the hit is a legitimate fixture or already patched.
3. **Emit the report.** Do not edit tests unless the caller explicitly asks.

## LLM Judgment

Use judgment only for:

- distinguishing a real violation from a legitimate fixture;
- writing a concrete replacement;
- deciding whether a hit is ERROR vs WARNING.

Do not add new categories or scan production code. If a test hit reveals a
production defect, add a one-line out-of-scope note; do not expand the scan.

## Output

```markdown
## Test Hygiene Report

### Hardcoded Dates
- ERROR|WARNING `<file>:<line>` — <why> — fix: <replacement>

### AsyncMock Misuse
- …

### Cross-Tier Truncates
- …

### Envelope Assertions
- …

### Singleton Leaks
- …

**Clean categories:** <list>
```

Use `No <category> found.` when a search is empty.

## Stop Conditions

- Stop if neither test root exists; report the missing path.
- Do not report production code or non-test files.
- Do not apply fixes without an explicit request.

## Token Budget

- Run the five searches exactly once; do not re-scan with variations.
- Default: open at most 20 surrounding-line windows. If there are more hits,
  triage the highest-severity 20 and report the remaining count as untriaged.
- Target ≤ 700 words; cite file:line, not full files. Summarize repeated hits.
