---
title: Configure your MCP client
description: Register godot-mcp in OpenCode, Claude, or any MCP host — stdio or HTTP.
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

## First call, sanity check

Ask the agent to run:

```
godot_health_check()       # → { bridge_connected, version }
godot_get_server_info()    # version, contract_version, toolsets, active scene, next_steps
```

`bridge_connected: true` means the editor addon is dialed in. If it's `false`:
open Godot with the addon enabled, check the status dock, then re-run.

Next: [your first session](first-session.md).