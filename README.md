# godot-mcp

A two-part system for **AI-driven Godot game development**. An AI client (Claude Code,
OpenCode, or any stdio MCP client) drives a live Godot editor through an MCP server.
The first concrete target is a tower-defense roguelite.

> **Status:** scaffolding (issue #1). The directory tree, dev bootstrap, and the bridge
> contract are in place; the WebSocket bridge and tools land in later issues. The 15 open
> GitHub issues are the authoritative spec — see `gh issue list`.

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
    godot_mcp.gd             EditorPlugin entry point (fleshed out in issue #2)
mcp_server/                  FastMCP server (Python 3.11+)
  main.py                    stdio entrypoint (bootstrapped in issue #4)
  tools/                     @mcp.tool() handlers (delegation only)
  resources/                 godot://… read-only resources (issue #11)
  prompts/                   workflow prompt templates (issue #12)
  models/                    Pydantic domain models (issue #7)
tests/
  contract/                  envelope shapes + tool schemas
  integration/               server ↔ fake/real bridge
  unit/                      isolated logic
docs/
  architecture.md            bridge contract + JSON envelope format
  tool-contracts.md          tool/resource/prompt schema spec
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

1. Open the `godot/` folder as a project in Godot **4.4+**.
2. Enable the addon: **Project → Project Settings → Plugins → godot_mcp → Enable**.
3. The status dock appears once issue #2 lands; the bridge listens on
   `ws://localhost:9080` by default (configurable, localhost-only, no auth in v1).

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
| `GODOT_MCP_LOG_LEVEL` | `INFO` | log level (JSON logs → stderr) |
| `GODOT_MCP_PERMISSION_MODE` | `ask` | tool permission mode (enforced in issue #14) |

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

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) and the path-scoped rules in
[`.claude/rules/`](.claude/rules/) first. The workflow is issue-driven: **issue → failing
test → green code → preflight clean → PR (`closes #N`) → merge**. Tests come before
implementation and the suite carries zero skips.
