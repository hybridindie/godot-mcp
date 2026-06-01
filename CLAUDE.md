# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The engine is built: scaffold (#1), addon + status dock (#2), WebSocket bridge (#3), FastMCP server (#4), read-only inspection tools (#5), the safety framework (#14), and safe scene mutation tools (#6) are merged. Remaining godot-mcp work: script read/patch (#10), `godot://` resources (#11), and the runtime loop (#13). The GitHub issues are the authoritative spec; read the relevant issue before implementing a piece.

**godot-mcp is a generic, game-agnostic Godot MCP server.** It exposes Godot editor capabilities (inspection, scene mutation, scripts, runtime) over MCP — it has no built-in game vocabulary. Any specific game (e.g. a tower-defense roguelite) is a **separate project** that consumes this server; its domain models, semantic tools, and prompts live in that project, not here.

## Grounding rules

The constitutional rules live in `.claude/rules/` and are the source of truth for *how* to build here. Each is path-scoped (frontmatter `paths:`) so it surfaces on the files it governs. Read the relevant rule before writing code in that area:

| Rule | Article | Governs |
|------|---------|---------|
| `architecture.md` | I & II | Library-first; the addon/server boundary (only the addon touches Godot, only the server owns safety) |
| `mcp-tools.md` | VI + safety | Tool/resource/prompt contract; safety classes, `dry_run`/`confirm`, preconditions |
| `error-handling.md` | IV | The versioned JSON envelope (`{id, ok, result, error, hint}`); structured errors |
| `async-patterns.md` | V | Async FastMCP; bridge timeouts, reconnect/backoff, `id` correlation |
| `addon.md` | — | GDScript addon: `@tool`, command router, UndoRedo, JSON-safe serialization, `type_coerce.gd` |
| `testing.md` | III | TDD; contract→integration→unit; suite health (zero skips) |
| `workflow.md` | — | Issue → red test → green → preflight → PR → merge pipeline |
| `enforcement.md` | IX | Gates, PR checklist, CalVer |

Adapted from the [hybridindie/instructions-and-rules](https://github.com/hybridindie/instructions-and-rules) harness, pared to this project: no frontend/database/Copilot-mirror rules (none apply), with an addon rule added for the GDScript half.

## What this is

A two-part system for **AI-driven Godot development**: an AI client (Claude Code and OpenCode are the primary targets; any stdio MCP client works) drives a live Godot editor through an MCP server. It is **game-agnostic** — generic Godot editor control, not tied to any one game. The repo deliberately keeps a clean boundary between the two halves.

## Architecture

The defining feature is a **four-layer transport chain** (issue #3). Every agent action crosses all four layers:

```
AI client (Claude Code / OpenCode / any stdio MCP client)
    │  stdio (MCP protocol)
FastMCP server  (Python, mcp_server/)
    │  WebSocket — localhost, default ws://localhost:9080
Godot EditorPlugin  (GDScript, godot/addons/godot_mcp/)
    │  Godot Editor API
Live Godot project
```

- **MCP server** (`mcp_server/`, Python 3.11+, FastMCP) — the AI-facing entry point over stdio. Exposes **tools**, **resources** (`godot://...` URIs, issue #11), and **prompts** (workflow templates, issue #12). It owns all safety/permission logic and Pydantic domain models; it holds **no** Godot logic itself — it forwards to the addon over the WebSocket bridge.
- **Godot addon** (`godot/addons/godot_mcp/`, GDScript, Godot 4.4+) — an `EditorPlugin` (`@tool`) that runs a `TCPServer`+`WebSocketPeer` server, routes incoming command envelopes to `cmd_*` handlers that call the Godot Editor API, and shows a status dock. This is the *only* layer that touches Godot.

A typical MCP tool is a thin wrapper: validate/typed-schema in Python → `bridge.send("cmd_name", params)` → addon `cmd_name` handler → JSON result back up the chain. When adding a capability you almost always implement **both** sides (issues tagged `[Both]`): the GDScript `cmd_*` handler and the FastMCP tool that routes to it.

### Planned layout (issue #1)

```
godot/addons/godot_mcp/    plugin.cfg, godot_mcp.gd (EditorPlugin), dock, cmd_* handlers, type_coerce.gd
mcp_server/                main.py (stdio entrypoint), tools/, resources/, prompts/, models/ (Pydantic)
docs/                      architecture.md (bridge contract), tool-contracts.md, domain-model.md
```

## Cross-cutting conventions

These span many files and are the things easiest to get wrong:

- **JSON envelopes** (issue #3) — versioned from day one. Command: `{ id, command, params }`. Response: `{ id, ok, result, error }`. Requests correlate by `id`. The bridge reconnects with exponential backoff; `ping`→`pong` is the health check.
- **Structured errors, never stack traces** — failures return `{ ok: false, error, hint }`. Preconditions return a richer form: `{ ok: false, error: "PRECONDITION_FAILED", hint, required }` (issue #14). Errors must be actionable for an agent with no human in the loop.
- **Tool safety classes** (issue #14) — every tool is tagged `read_only` | `mutating` | `destructive` | `runtime`. `mutating`/`destructive` tools take `dry_run: bool = False`; `destructive` tools require `confirm=True`. Common preconditions: `require_active_scene`, `require_bridge_connected`, `require_node_exists(path)`. All safety logic lives in the MCP layer, **not** the addon.
- **UndoRedo for every mutation** (issue #6) — all create/rename/delete/set operations in the addon must register with `EditorUndoRedoManager`.
- **JSON-safe serialization** — the scene tree and node properties must serialize to JSON-safe types only (no Godot objects). Large trees support a `max_depth` parameter.
- **Type coercion** (issue #6) — Godot types (`Vector2/3`, `Color`, `Rect2`, `NodePath`) are coerced to/from JSON in a dedicated `type_coerce.gd` helper, not inline.
- **Read-only vs. mutating split** — read-only context is exposed both as tools (issue #5) and as `godot://` resources (issue #11); mutations only ever go through tools.
- **Naming** — `snake_case` for all domain/data fields and Pydantic models; addon command handlers are `cmd_<verb>_<noun>`; matching MCP tools drop the `cmd_` prefix.

## Game-agnostic scope

godot-mcp deliberately ships **no** game vocabulary — no Tower/Enemy/Wave models, no `create_tower`-style tools or prompts. Its surface is generic Godot: inspection, scene mutation, scripts, resources, and runtime control. A specific game (a tower-defense roguelite is the first consumer) is a **separate project** that imports godot-mcp as an MCP server and layers its own domain models, semantic tools, and prompts on top. Keep that boundary: if a capability only makes sense for one game, it belongs in the game project, not here.

## Toolchain & running

The scaffold (issue #1) is in place: `uv`-managed Python package, the addon under `godot/`, docs, and CI.

- Godot **4.4+**; Python **3.11+**; **FastMCP** (PrefectHQ/fastmcp) as the MCP framework, managed with **uv**. Always verify Godot APIs against the current docs for the pinned version (via `context7` or `docs.godotengine.org`) rather than from memory — see [[addon]].
- **Dev commands** (run from repo root, mirrored by `.github/workflows/ci.yml`):
  - `uv sync` — create the venv and install runtime + dev deps.
  - `uv run pytest -q` — full suite; single file `uv run pytest tests/unit/test_smoke.py`; single test `uv run pytest tests/unit/test_smoke.py::test_version_is_calver`.
  - `uv run ruff check .` — lint; `uv run mypy` — type check.
  - `./.claude/hooks/check-no-skipped-tests.sh` — zero-skip suite-health gate.
- Server entrypoint: `uv run godot-mcp` (stdio). It currently exits with a "not yet bootstrapped" message; the FastMCP server and the `health_check` tool (server version + bridge connection state) land in issue #4.
- The addon is enabled via Godot's *Project Settings → Plugins* (open the `godot/` folder as a project); the bridge defaults to `ws://localhost:9080` (configurable). No auth in v1 (localhost-only).
- Clients register the server as a local stdio MCP command: Claude Code via `.mcp.json` / `claude mcp add`, OpenCode via `opencode.json`. Document concrete examples for both once the entrypoint is bootstrapped (issue #4).
