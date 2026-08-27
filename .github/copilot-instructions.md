# godot-mcp Copilot Instructions

This project is a **Godot MCP server** — it drives a live Godot editor from AI agents over the Model Context Protocol.

## Setup

1. Install the package: `pip install godot-editor-mcp --pre`
2. Open a Godot 4.4+ project with the `godot_mcp` addon enabled (copy `godot/addons/godot_mcp/` into your project's `addons/`)
3. The addon connects out to `ws://127.0.0.1:9080` (the MCP server's bridge listener)

## Key files

- `AGENTS.md` — project entry point, architecture, conventions, grounding rules
- `.opencode/rules/` — constitutional rules (architecture, safety, testing, workflow)
- `docs/tool-contracts.md` — the tool surface (175 tools across 29 categories)
- `docs/tutorial.md` — LLM-prompt tutorial for building a game
- `skills/` — installable AI skills (`./scripts/install-skills.sh`)

## Workflow

Follow the issue-driven pipeline: issue → red test → green → preflight → PR → merge.
Run `./.opencode/hooks/check-no-skipped-tests.sh` to verify suite health.

## Dev commands

- `uv sync` — install deps
- `uv run pytest -q` — full test suite
- `uv run ruff check .` — lint
- `uv run mypy` — type check
- `uv run godot-editor-mcp` — start the MCP server

## Safety classes

- `read_only` — never mutates
- `mutating` — takes `dry_run=True` for preview
- `destructive` — requires `confirm=True`
- `runtime` — controls game execution

## Rules

Read `.opencode/rules/` before writing code. The rules are path-scoped and govern:
architecture (addon/server boundary), MCP tool contracts, error handling, async patterns,
GDScript addon conventions, testing (TDD), workflow, and enforcement.