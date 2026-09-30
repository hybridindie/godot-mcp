---
type: index
title: "Configure your MCP client"
description: "Register godot-mcp in OpenCode, Claude, or any MCP host — stdio or HTTP."
created: 2026-09-19
updated: 2026-09-23
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

!!! warning "Some clients don't refresh their tool list after a toggle"
    `enable_toolset` mutates the served surface and the server emits the
    spec-required `notifications/tools/list_changed` (it advertises
    `tools.listChanged: true` and delivers the notification on both protocol
    eras). But a client caches the tool list and must act on that notification
    to pick up newly-enabled tools — and several don't. As of this writing,
    Claude Code has open bugs where the notification is a no-op
    ([#88483](https://github.com/anthropics/claude-code/issues/88483),
    [#88172](https://github.com/anthropics/claude-code/issues/88172)); OpenCode
    had the same class of bug
    ([#48196](https://github.com/anomalyco/opencode/issues/48196)).

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

## First call, sanity check

Ask the agent to run:

```
godot_health_check()       # → { bridge_connected, version }
godot_get_server_info()    # version, contract_version, toolsets, active scene, next_steps
```

`bridge_connected: true` means the editor addon is dialed in. If it's `false`:
open Godot with the addon enabled, check the status dock, then re-run.

Next: [your first session](getting-started-first-session.md).