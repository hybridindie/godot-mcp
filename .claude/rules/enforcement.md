---
read_when: "Checking which gates CI runs, changing a gate, or cutting a CalVer release"
paths:
  - "**/*"
---

# Enforcement & Versioning

These rules are the project's grounding contract. A change that violates one is not "done."

## Gates

| Gate | Blocks on |
|------|-----------|
| Workflow ([[workflow]]) | A skipped step — no issue, test-after-code, bundled drive-by fix, unaddressed review comment |
| Suite health ([[testing]]) | Any failing/erroring test or forbidden skip. Run `.claude/hooks/check-no-skipped-tests.sh` (wired into CI) |
| Harness (`guardrails.sh --ci`) | A secret in the tree, Claude/OpenCode mirror drift, or a rule missing from the `AGENTS.md` index |
| Type check | New `mypy` / type errors in changed Python |
| Lint | `ruff` errors |
| Bridge contract ([[error-handling]]) | An envelope shape change without a contract-test update |
| Safety classes ([[mcp-tools]]) | A `mutating`/`destructive` tool missing `dry_run`/`confirm`, or safety logic placed in the addon |
| camelCase gate | A tool name that breaks the `godot_<toolset>_<action>` transform contract (scoped to the transform contract tests) |
| Godot 4.4 floor (`godot-floor` in `ci.yml`) | The addon does not parse, or its headless smokes fail, on the supported 4.4 floor |
| Live-editor e2e (`e2e.yml`) | Addon/server smoke against a real Godot editor on the self-hosted runner |
| Godot 4.8 beta lane (`e2e.yml`, advisory) | Addon/bridge/integration regressions on the pinned `4.8-beta1` binary — visible but non-blocking until `4.8-stable` |

CI runs all gates above via `.github/workflows/ci.yml` (zero-skip, harness, lint, mypy, pytest, camelCase gate, Godot 4.4 floor) plus `e2e.yml` (live-editor smoke on a self-hosted runner, including the advisory 4.8-beta lane) and `publish.yml` (PyPI + GitHub release on tag). Keep this table in sync with what CI actually runs.

## Anti-patterns

- Unexplained deviation from a rule above (deviate only with a stated reason in the PR).
- Code changes that leave `docs/` or this rule set stale.

## Versioning

CalVer `YYYY.MM.DD[.N]` (a dotted `.N` is a same-day revision). The version lives in `pyproject.toml`; read it there.
