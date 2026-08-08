---
description: Run the full preflight gate (zero-skip, ruff, ruff format, mypy, pytest) — workflow step 4 before a PR
agent: build
---

Run the project's preflight gate — the exact sequence CI runs (`.github/workflows/ci.yml`) and workflow step 4 requires before a PR. Run each check in order and stop at the first failure.

Execute, in order, and report each result:

1. **Zero-skip gate** — `./.opencode/hooks/check-no-skipped-tests.sh`
2. **Lint** — `uv run ruff check .`
3. **Format check** — `uv run ruff format --check .`
4. **Type check** — `uv run mypy`
5. **Tests** — `uv run pytest -q`
6. **camelCase regression gate (compat bridge off)** — `FASTMCP_MCP_CAMELCASE_COMPAT=false uv run pytest -q`
7. **Addon touched?** — if any file under `godot/addons/godot_mcp/` changed, note that the human should load the plugin in Godot 4.4+ and confirm it enables/disables without errors (per `@.opencode/rules/workflow.md` step 4). You cannot run Godot; just flag it.

Rules:
- Run the checks yourself with bash; do not ask the user to run them.
- Stop at the first failing check and surface its output verbatim — do not continue to later gates (each step gates the next, per `@.opencode/rules/enforcement.md`).
- If all checks pass, report "Preflight clean — ready for PR (workflow step 4)" and stop. Do not open a PR unless explicitly asked.
- If a check fails, diagnose the failure against the relevant rule (`testing.md`, `enforcement.md`), propose the minimal fix, and stop. Wait for the user before applying.
- Never skip a check or lower a threshold to make preflight pass.