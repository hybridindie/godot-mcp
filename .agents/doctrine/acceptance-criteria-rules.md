<!--
  acceptance-criteria-rules.md — Shared linting rules for acceptance criteria
  Referenced by: epic-acceptance-linter, epic-composer
  version: 1.2.0, owner: John D
  Single source of truth for the six linting rules. Optional quality passes
  reuse them; skills apply them; nothing restates them.
-->

# Acceptance Criteria Rules

Acceptance criteria should be clear, concise, specific, testable
(yes/no or pass/fail), aligned with user and business outcomes, and realistic
within constraints.

## The six linting rules

For each acceptance criterion, check:

1. **Observability**
   - Can someone observe or measure whether this criterion is satisfied?
   - Does it avoid internal or unobservable states?

2. **Testability**
   - Can this criterion be validated with a straightforward yes/no or pass/fail test?
   - Could a tester or automated test reasonably implement verification?

3. **Specificity**
   - Is the behavior or outcome described precisely?
   - Does it avoid vague phrases like "easy", "fast", "intuitive", "robust", or "user-friendly"?
   - If such terms appear, are they backed by thresholds or examples?
   - Does it name the actor, trigger and condition?
   - Is it bounded by the non-functional constraint it depends on (latency,
     volume, permission)?

4. **Outcome focus**
   - Does the criterion describe an outcome rather than an implementation step?

5. **Non-conflict**
   - Is the criterion consistent with other criteria and the Epic's scope?
   - If criteria conflict, surface that conflict rather than resolving silently.

6. **Coverage**
   - Do the criteria collectively cover the main success path, alternate paths,
     key edge cases, and validation or permission aspects?
   - Edges to check: empty, invalid, duplicate, permission denied, timeout,
     partial failure.

## Example lints

**Weak:** "The export feature is fast and user-friendly."
- Specificity / Observability: "fast" and "user-friendly" have no threshold.
- **Strengthened:** "When a user exports a report under 500 rows, the PDF
  downloads within 10s at p95."

**Weak:** "The API returns order history as JSON."
- Outcome focus: describes implementation, not observable value.
- **Strengthened:** "When a signed-in user opens Order History, their orders
  from the last 12 months are listed newest-first."

## Behavior rules for callers

- Prefer strengthening existing criteria over adding many new ones.
- Do not fabricate thresholds or metrics not supported by source material.
  If the source provides none, mark the threshold [UNKNOWN] rather than inventing.
- When criteria are too vague for any of these rules to apply, the caller should
  hand off to the epic-interview skill for clarity
  rather than guessing.

## How callers use this file

- `epic-acceptance-linter` applies these rules and may end with an optional
  Ready / Needs work / Blocked verdict — advice, not a gate.
- `epic-composer` and `story-decomposer` apply them while drafting.
- The optional quality passes reuse them without restating them.