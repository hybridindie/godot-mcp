---
paths:
  - "**/*"
---

# Enforcement & Versioning (Article IX)

These rules are the project's grounding contract. A change that violates one is not "done."

## Gates

| Gate | Blocks on |
|------|-----------|
| Workflow ([[workflow]]) | A skipped step — no issue, test-after-code, bundled drive-by fix, unaddressed review comment |
| Suite health ([[testing]]) | Any failing/erroring test or forbidden skip. Run `./.opencode/hooks/check-no-skipped-tests.sh` (wired into CI) |
| Type check | New `mypy` / type errors in changed Python |
| Lint | `ruff` errors |
| Bridge contract ([[error-handling]]) | An envelope shape change without a contract-test update |
| Safety classes ([[mcp-tools]]) | A `mutating`/`destructive` tool missing `dry_run`/`confirm`, or safety logic placed in the addon |
| camelCase gate | A tool name that breaks the `godot_<toolset>_<action>` transform contract (scoped to the transform contract tests) |
| Live-editor e2e (`e2e.yml`) | Addon/server smoke against a real Godot editor on the self-hosted runner |

CI runs all gates above via `.github/workflows/ci.yml` (zero-skip, lint, mypy, pytest, camelCase gate) plus `e2e.yml` (live-editor smoke on a self-hosted runner) and `publish.yml` (PyPI + GitHub release on tag). Keep this table in sync with what CI actually runs.

## PR acceptance checklist

- [ ] **Workflow**: issue referenced (`closes #N`); test was red before the fix; preflight clean; comments resolved
- [ ] **Architecture** ([[architecture]]): handlers are delegation-only; only the addon touches Godot; only the server owns safety
- [ ] **Tools** ([[mcp-tools]]): typed I/O, `safety_class` set, preconditions checked
- [ ] **Errors** ([[error-handling]]): failures return `{ ok:false, error, hint }`, not traces
- [ ] **Async** ([[async-patterns]]): async handlers, bridge timeouts + reconnect, no import-time I/O
- [ ] **Addon** ([[addon]]): `@tool`, UndoRedo on mutations, JSON-safe serialization
- [ ] **Tests** ([[testing]]): failing test first, tier coverage met, zero skips
- [ ] Docs updated when a contract or structure changes (`docs/architecture.md`, `docs/tool-contracts.md`)

## Anti-patterns

- Unexplained deviation from a rule above (deviate only with a stated reason in the PR).
- Code changes that leave `docs/` or this rule set stale.

## Versioning

CalVer `YYYY.MM.DD[-N]`. Current: **2026.09.02** (first stable).
