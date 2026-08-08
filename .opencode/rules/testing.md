---
paths:
  - "mcp_server/**/*.py"
  - "tests/**/*.py"
  - "godot/addons/godot_mcp/**/*.gd"
---

# Testing: TDD Mandate (Article III)

Code is written only after a failing test pins the behavior. Every bug gets a regression test before its fix.

## Authoring order

**Contract → Integration → Unit.**

| Layer | Purpose | Location |
|-------|---------|----------|
| Contract | Envelope shapes and tool schemas (a `ping`→`pong`, a tool's typed I/O) | `tests/contract/` |
| Integration | Server ↔ a fake/real bridge; precondition and safety paths | `tests/integration/` |
| Unit | Isolated logic — `type_coerce`, backoff, model validation | `tests/unit/` |

The bridge is the seam most worth a contract test: assert the JSON envelope (`id`, `ok`, `error`, `hint`) against a fake addon peer so server logic is testable without a running editor.

## Coverage tiers

| Component | Minimum |
|-----------|---------|
| Safety / precondition logic (`safety.py`) | 90%+ |
| Tool & bridge logic | 70%+ |
| Domain models, helpers | 50%+ |

## Suite health (BLOCKING)

- Zero failing or erroring tests checked in. A clean-checkout run of the suite exits zero.
- Zero unconditional skips: no `@pytest.mark.skip`, no `xfail`, no bare `pytest.skip("not implemented")`. Fix the code or delete the test. Conditional `skipif` is allowed only on a genuine environmental precondition (e.g. "Godot binary not installed").
- Determinism is mandatory: inject `Clock` / fake bridge — no `asyncio.sleep()` waits, no real sockets in unit tests, no wall-clock or RNG dependence.
- Test drift is a bug: change a tool's schema or an envelope field and update its tests in the same commit.

## Anti-patterns

- Tests written after the implementation passes.
- A bug fix with no regression test.
- Asserting against a hand-built dict that doesn't match the real envelope shape.
- Mocking the bridge so loosely the test would pass against a broken transport.
