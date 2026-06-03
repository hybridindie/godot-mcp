# godot-mcp

A **generic, game-agnostic** system for **AI-driven Godot development**. An AI client
(Claude Code, OpenCode, or any stdio MCP client) drives a live Godot editor through an MCP
server — generic editor control (inspection, scene mutation, scripts, runtime), with no
built-in game vocabulary. A specific game is a separate project that consumes this server.

> **Status:** feature-complete across the planned ecosystem — inspection, scene mutation,
> scripts, resources, project/filesystem, screenshots, the full content domains (physics,
> animation, 3D, particles, navigation, audio, tilemap, theme/UI, shaders), the runtime
> session bridge (live inspection, input simulation/recording, profiling), play-testing/QA,
> batch refactor, static analysis, and export are all merged. 116 tools across 22 gated
> toolsets (plus always-on `core`). See [`docs/tool-contracts.md`](docs/tool-contracts.md)
> for the full surface.

## Architecture

Every agent action crosses a four-layer transport chain (see
[`docs/architecture.md`](docs/architecture.md)):

```
AI client (Claude Code / OpenCode / any stdio MCP client)
    │  stdio (MCP protocol)
FastMCP server  (Python, mcp_server/)
    │  WebSocket — localhost, default ws://localhost:9080
Godot EditorPlugin  (GDScript, godot/addons/godot_mcp/)
    │  Godot Editor API
Live Godot project
```

### Two halves, one seam

| Half | Path | Responsibility |
|------|------|----------------|
| **MCP server** | `mcp_server/` | The AI-facing entry point over stdio. Exposes tools, resources (`godot://…`), and prompts. Owns **all** safety, permission, and precondition logic plus the Pydantic domain models. Holds **no** Godot logic — it forwards to the addon over the WebSocket bridge. |
| **Godot addon** | `godot/addons/godot_mcp/` | An `EditorPlugin` (`@tool`) that runs a `TCPServer` + `WebSocketPeer`, routes incoming command envelopes to `cmd_*` handlers that call the Godot Editor API, and shows a read-only status dock. The **only** layer that touches Godot. |

A typical tool is a thin wrapper: validate a typed schema in Python →
`bridge.send("cmd_name", params)` → addon `cmd_name` handler → JSON result back up the
chain. Most capabilities are implemented on **both** sides.

The boundary is deliberate and enforced by the rules in
[`.claude/rules/`](.claude/rules/): only the addon touches Godot, only the server owns
safety.

## Repository layout

```
godot/
  project.godot              minimal Godot project so the addon is loadable
  addons/godot_mcp/
    plugin.cfg               addon manifest (Godot 4.4+)
    godot_mcp.gd             EditorPlugin entry point (dock, bridge, debugger plugin)
    mcp_bridge.gd            TCPServer + WebSocketPeer; receives command envelopes
    command_router.gd        routes cmd_* envelopes to handlers (the only Godot-touching code)
    mcp_dock.gd              read-only status dock (connection/scene/recent commands)
    scene_inspect.gd         JSON-safe scene-tree / node serialization
    type_coerce.gd           Godot ↔ JSON type coercion (Vector2/3, Color, …)
    mcp_debugger.gd          EditorDebuggerPlugin: captures a played game's godot_mcp channel
    mcp_runtime_probe.gd     game-side autoload for live runtime inspection/input (see below)
mcp_server/                  FastMCP server (Python 3.11+)
  main.py                    stdio / Streamable-HTTP entrypoint
  server.py                  server factory: wires the bridge + registers all tool groups
  bridge.py                  async WebSocket client (id correlation, timeout, backoff)
  toolsets.py / categories.py  the gated toolset system (enable_toolset)
  safety.py                  safety classes, preconditions, dry_run/confirm
  runtime.py                 headless run / export subprocess (GodotRunner)
  qa.py / analysis.py        play-testing + static-analysis logic (pure, off the bridge)
  tools/                     @mcp.tool() handlers (delegation only)
  resources/                 godot://… read-only resources
  models/                    Pydantic typed tool I/O
  prompts/                   reserved (no prompts shipped — the planned set was game-specific)
tests/
  contract/                  envelope shapes + tool schemas (fake bridge)
  integration/               live headless-editor e2e (skipped when Godot isn't installed)
  unit/                      isolated logic
docs/
  architecture.md            bridge contract, JSON envelope, runtime session bridge
  tool-contracts.md          the full tool/resource surface, per toolset
```

## Local dev setup

### Prerequisites

- **Godot 4.4+** — the addon targets the Godot 4.4 editor API.
- **Python 3.11+** — the MCP server.
- **[uv](https://docs.astral.sh/uv/)** — Python dependency manager (the documented path).

### Bootstrap (Python / MCP server)

This project uses **uv**. From the repo root:

```bash
uv sync                       # create the venv and install runtime + dev deps
uv run pytest                 # run the full test suite
uv run pytest tests/unit/test_smoke.py            # a single test file
uv run pytest tests/unit/test_smoke.py::test_version_is_calver   # a single test
uv run ruff check .           # lint
uv run mypy                   # type check
```

<details>
<summary>pip + venv fallback (no uv)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'       # or: pip install -e . then install dev tools
pytest
```
</details>

### Bootstrap (Godot / addon)

1. Open the `godot/` folder as a project in Godot **4.4+** (or copy `addons/godot_mcp/`
   into your own project's `addons/`).
2. Enable the addon: **Project → Project Settings → Plugins → godot_mcp → Enable**.
3. A read-only status dock appears (connection state, project/scene/selected node, recent
   commands); the bridge listens on `ws://localhost:9080` by default (configurable,
   localhost-only, no auth in v1).

### Running the server

```bash
uv run godot-mcp                      # stdio (default)
GODOT_MCP_TRANSPORT=http uv run godot-mcp   # Streamable HTTP on 127.0.0.1:9090
```

`python -m mcp_server.main` is the equivalent module invocation. (Running
`python mcp_server/main.py` directly does **not** work — the package uses absolute
imports, so use the console script or `-m`.)

Configuration (all optional, env vars):

| Var | Default | Meaning |
|-----|---------|---------|
| `GODOT_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `GODOT_MCP_HTTP_HOST` / `GODOT_MCP_HTTP_PORT` | `127.0.0.1` / `9090` | HTTP bind (when `transport=http`) |
| `GODOT_MCP_BRIDGE_URL` | `ws://localhost:9080` | Godot addon WebSocket URL |
| `GODOT_MCP_GODOT_BIN` | auto-discovered | Godot executable for headless run/export (else `PATH` / known locations) |
| `GODOT_MCP_PROJECT_DIR` | connected editor's project | project dir for the runner, export, and static analysis |
| `GODOT_MCP_LOG_LEVEL` | `INFO` | log level (JSON logs → stderr) |
| `GODOT_MCP_PERMISSION_MODE` | `ask` | reserved permission mode (plumbed in config; not yet enforced — safety is via per-tool classes + `dry_run`/`confirm`) |

### Connecting an MCP client

The server registers as a local **stdio** MCP command. The `health_check` tool reports
server version and Godot bridge connection state.

**OpenCode** (`opencode.json`):

```json
{
  "mcp": {
    "godot": {
      "type": "local",
      "command": ["uv", "run", "godot-mcp"]
    }
  }
}
```

**Claude Code** (`.mcp.json`, or `claude mcp add godot -- uv run godot-mcp`):

```json
{
  "mcpServers": {
    "godot": {
      "command": "uv",
      "args": ["run", "godot-mcp"]
    }
  }
}
```

Both assume the command runs from the repo root (so `uv` resolves this project's
environment). Use an absolute path or a `--directory` if launching elsewhere.

## Toolsets (keeping the tool surface small)

With ~116 tools, exposing them all at once would degrade an agent's tool selection, so
tools are grouped into **toolsets** and most are **gated off by default**. Only `core`
(diagnostics + toolset management) and `inspection` are exposed initially. The agent turns
others on at runtime with the always-available meta-tools:

- `list_toolsets` — discover the toolsets and which are enabled.
- `enable_toolset(category)` / `disable_toolset(category)` — expose/hide a toolset's tools
  (fires `tools/list_changed`). This only changes tool *exposure*; it never touches the project.

Available toolsets: `inspection`, `scene_edit`, `scripts`, `resources_edit`, `project`,
`editor`, `physics`, `animation`, `scene_3d`, `particles`, `navigation`, `audio`, `tilemap`,
`theme_ui`, `shader`, `runtime`, `input`, `testing`, `profiling`, `batch`, `analysis`,
`export`. Each tool is tagged with one category and a **safety class**
(`read_only` / `mutating` / `destructive` / `runtime`); `mutating`/`destructive` tools take
`dry_run`, and `destructive` ones require `confirm=true`. `list_tools_by_safety_class`
reports the grouping. See [`docs/tool-contracts.md`](docs/tool-contracts.md) for the full,
per-toolset surface.

## Live runtime tools (the probe autoload)

Inspecting or driving a **running** game — the `runtime` tools (`play_scene`,
`get_game_scene_tree`, `monitor_property`, `find_ui_elements`), `input`
(`simulate_*`, `play_input_sequence`, `record_input`), `testing`, and the live half of
`profiling` — works by launching the game **from the editor** so it connects to the editor's
debugger. Because a custom debugger plugin can't read the engine's remote tree, the running
game must cooperate via a small **probe autoload** that godot-mcp ships:

1. In your game's project, add `res://addons/godot_mcp/mcp_runtime_probe.gd` as an
   **autoload** (Project → Project Settings → Globals/Autoload). Any node name works.
2. Then `play_scene` → the probe connects, and the runtime/input/profiling tools work
   against the live game. It no-ops outside a debug session, so it's safe to leave enabled.

Without the probe, those tools report `connected: false` (with a hint) rather than failing —
the editor-control, scene-edit, and static tools need no probe. (`run_and_capture` and
`export_project` instead run Godot as a headless subprocess and don't use the probe.)

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) and the path-scoped rules in
[`.claude/rules/`](.claude/rules/) first. The workflow is issue-driven: **issue → failing
test → green code → preflight clean → PR (`closes #N`) → merge**. Tests come before
implementation and the suite carries zero skips.
