---
type: index
title: "Configure your MCP client"
description: "Register godot-mcp in OpenCode, Claude, or any MCP host — stdio or HTTP."
created: 2026-09-19
updated: 2026-10-10
---

# Configure your MCP client

## OpenCode (stdio — the default path)

`opencode.json` in the project root (or `~/.config/opencode/opencode.json`):

```json
{
  "mcp": {
    "godot": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/godot-mcp", "godot-editor-mcp"]
    }
  }
}
```

Or with a PyPI install:

```json
{
  "mcp": {
    "godot": {
      "type": "local",
      "command": ["godot-editor-mcp"]
    }
  }
}
```

## OpenCode (HTTP — shared service)

When the server runs as a long-lived HTTP service (several clients, one
editor):

```json
{
  "mcp": {
    "godot": {
      "type": "remote",
      "url": "http://127.0.0.1:9090/mcp"
    }
  }
}
```

With a token (non-loopback / Docker):

```json
{
  "mcp": {
    "godot": {
      "type": "remote",
      "url": "http://<host>:9090/mcp",
      "headers": { "Authorization": "Bearer <GODOT_MCP_AUTH_TOKEN>" }
    }
  }
}
```

## Other clients

Any MCP client works the same way — the server speaks standard MCP over stdio
or Streamable HTTP:

- **Claude Code / Claude Desktop**: add the same `command` (or `url`) shape in
  the client's MCP config.
- **Programmatic (Python)**: the MCP SDK's stdio client spawns
  `godot-editor-mcp` and speaks JSON-RPC over stdin/stdout.

!!! note "Sessions are stateless"
    godot-mcp serves the sessionless MCP `2026-07-28` protocol shape: no
    per-session state, and toolset grants are server-global. A reconnect keeps
    the grant — nothing to re-establish.

!!! warning "Most clients don't refresh their tool list after a toggle"
    `godot_enable_toolset` opens the gate server-side, but the server can only
    *announce* the change: `notifications/tools/list_changed` is a standard MCP
    notification, and whether the client re-runs `tools/list` is a **client
    choice** — the spec never makes re-listing a `MUST`. In practice **most MCP
    hosts cache the tool list at session start and ignore the notification**, so
    the newly-enabled tools never reach the model. Treat the gate as server
    state the agent *pulls*, not a push the client must honor.

    **If your client hits this: pre-enable the toolsets at server startup**, so
    the *initial* `tools/list` already contains them and no refresh is needed:

    ```jsonc
    // same MCP entry — add an env block to the server command
    {
      "mcp": {
        "godot": {
          "type": "local",
          "command": ["godot-editor-mcp"],
          "env": { "GODOT_MCP_DEFAULT_TOOLSETS": "scene_edit,scripts,physics,runtime" }
        }
      }
    }
    ```

    `GODOT_MCP_DEFAULT_TOOLSETS` takes a comma-separated category list, or
    `all` for the full surface. It seeds the enabled set before the client's
    first `tools/list`, so the toolsets are present from the start.
    `enable_toolset` still works normally at runtime.

## Which clients refresh their tool list?

Surveyed October 2026. **Supports** = receives the change and re-runs
`tools/list` without a reconnect; **partial** = a mechanism exists but is
capability-gated or only some code paths use it; **does not** = caches
`tools/list` at session start.

| Client | Verdict |
|--------|---------|
| OpenCode | **supports** — re-lists every LLM step |
| Google Gemini CLI | **supports** (buggy refresh path) |
| Block Goose | **supports** |
| Cline (VS Code extension) | **supports** |
| VS Code + Copilot Chat | **supports** (can lag to the next turn) |
| Claude Code (CLI) | **partial** — only subscribes when the server advertises `tools.listChanged: true` (see below) |
| Zed | **partial / conflicting** |
| Claude Code Desktop app | **does not** |
| OpenAI Codex CLI | **does not** |
| Cursor (IDE + CLI) | **does not** |
| Continue | **does not** |
| Roo Code | **does not** |
| Cline (CLI) | **does not** |
| Qwen Code | **does not** |
| LibreChat | **does not** |
| Claude Desktop · Windsurf/Devin Desktop · Open WebUI · Jan · Msty · Chatbox | **unknown** |
| Python / TypeScript SDK · FastMCP client | **partial** — surface the event; re-listing is the caller's job |

Transport compounds this: **stdio is the best-tested path**, while
Streamable-HTTP has seen more refresh regressions. The local stdio default is
the safer configuration.

### The advertisement gotcha

A capable client (Claude Code's CLI) subscribes only when the server's
handshake advertises `capabilities.tools.listChanged: true`. On the
`2026-07-28` sessionless protocol MCP derives that flag from whether the server
serves a `subscriptions/listen` stream. godot-mcp now serves it — it registers
the mcp SDK's `ListenHandler` on FastMCP's low-level server, the same wiring
mcp's own `MCPServer` uses — so the modern `server/discover` advertises
`tools.listChanged: true` and a subscribing client receives
`notifications/tools/list_changed` after `godot_enable_toolset`
([#620](https://github.com/hybridindie/godot-mcp/issues/620)). Clients that
ignore the notification or never open a listen stream still need the pre-load
workaround above.

Beyond the push, `godot_enable_toolset` returns the enabled tools' names,
descriptions, and input schemas
([#621](https://github.com/hybridindie/godot-mcp/issues/621)), so the agent can
use them even when its registry never refreshes.

## First call, sanity check

Ask the agent to run:

```
godot_health_check()       # → { bridge_connected, version }
godot_get_server_info()    # version, contract_version, toolsets, active scene, next_steps
```

`bridge_connected: true` means the editor addon is dialed in. If it's `false`:
open Godot with the addon enabled, check the status dock, then re-run.

Next: [your first session](getting-started-first-session.md).