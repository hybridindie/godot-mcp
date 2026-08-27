# Contributing to godot-mcp

Thanks for your interest in contributing! godot-mcp is a standalone MCP server that drives a live Godot editor from AI agents. This guide covers setup, workflow, and conventions.

## Prerequisites

- **Python 3.11+** managed with [uv](https://docs.astral.sh/uv/)
- **Godot 4.4+** (validated on 4.7-stable)
- **FastMCP 4.0** (pinned to the 4.0 beta)

## Setup

```bash
git clone https://github.com/hybridindie/godot-mcp.git
cd godot-mcp
uv sync
```

For the knowledge graph (optional, developers only):
```bash
cp .env.dev.example .env
# Adjust OLLAMA_MODEL to a model you have pulled
set -a; . ./.env; set +a
```

## Development commands

```bash
uv run pytest -q                    # full test suite
uv run pytest tests/unit/test_smoke.py  # single file
uv run ruff check .                 # lint
uv run mypy                         # type check
./.opencode/hooks/check-no-skipped-tests.sh  # zero-skip suite health gate
uv run godot-editor-mcp             # start the MCP server (stdio)
```

## Workflow

Follow the issue-driven pipeline (see `.opencode/rules/workflow.md`):

1. **Issue exists** — every merge traces to a GitHub issue
2. **Failing test** — write a red test that pins the behavior or reproduces the bug
3. **Green code** — minimum change to pass
4. **Preflight clean** — `pytest`, `mypy`, `ruff`, zero-skip scan all green
5. **PR opened** — title `<type>(<scope>): <summary> (closes #N)`, body has acceptance criteria + test plan
6. **Comments addressed** — the Qodo PR bot auto-runs `/describe` + `/review`; wait for it, then fix or reply to every finding
7. **Merge** — squash, delete branch

## Grounding rules

The constitutional rules live in `.opencode/rules/` and are the source of truth for how to build here. Read the relevant rule before writing code in that area:

| Rule | Governs |
|------|---------|
| `architecture.md` | Library-first; the addon/server boundary |
| `mcp-tools.md` | Tool/resource/prompt contract; safety classes |
| `error-handling.md` | The versioned JSON envelope; structured errors |
| `async-patterns.md` | Async FastMCP; bridge timeouts, reconnect |
| `addon.md` | GDScript addon conventions (`@tool`, UndoRedo, serialization) |
| `testing.md` | TDD mandate; suite health (zero skips) |
| `workflow.md` | Issue → red test → green → preflight → PR → merge |
| `enforcement.md` | Gates, PR checklist, versioning |

## Architecture

Two halves joined by a WebSocket bridge:

```
AI client ──stdio──> FastMCP server (Python) ──WebSocket──> Godot addon (GDScript) ──> live project
```

- **MCP server** (`mcp_server/`) — owns all safety/permission logic, Pydantic models, and tool schemas. Never touches Godot directly.
- **Godot addon** (`godot/addons/godot_mcp/`) — the only layer that touches the Godot Editor API. Routes commands to `cmd_*` handlers.

When adding a capability, implement **both** sides: the GDScript `cmd_*` handler and the FastMCP tool that routes to it.

## Safety classes

Every tool is tagged:

| Class | Meaning | Requirements |
|-------|---------|-------------|
| `read_only` | Never mutates | None |
| `mutating` | Reversible (UndoRedo) | `dry_run: bool = False` |
| `destructive` | May be irreversible | `dry_run` + `confirm: bool = True` |
| `runtime` | Controls game execution | — |

## Testing

TDD is mandated (see `.opencode/rules/testing.md`):

- **Contract** — envelope shapes and tool schemas (`tests/contract/`)
- **Integration** — server ↔ fake bridge; precondition and safety paths (`tests/integration/`)
- **Unit** — isolated logic, models, helpers (`tests/unit/`)
- **GDScript** — GUT tests for addon behavior (`godot/tests/`, `examples/*/tests/`)

Zero skips are a blocking gate. No `@pytest.mark.skip`, no `xfail`, no bare `pytest.skip()`.

## Skills

Three AI skills ship in `skills/` — installable into any AI client:

```bash
./scripts/install-skills.sh          # opencode (default)
./scripts/install-skills.sh --target ~/.claude/skills  # Claude
```

See [`skills/README.md`](skills/README.md) for details.

## Versioning

CalVer `YYYY.MM.DD[-N]` with PEP 440 prerelease suffixes (e.g. `2026.08.26b1`). The version is in `pyproject.toml`, `mcp_server/__init__.py`, and `godot/addons/godot_mcp/plugin.cfg` — all three must stay in lockstep.

## Publishing

Releases are automated via `.github/workflows/publish.yml` — triggered on GitHub release publish. See [the release workflow](infra/README.md) for details.

## Questions?

Open an [issue](https://github.com/hybridindie/godot-mcp/issues) or read [`AGENTS.md`](AGENTS.md) for the full project context.