---
type: index
title: "Install the Godot addon"
description: "Copy the addon into your project and enable it — the editor dials the server and reconnects on its own."
created: 2026-09-19
updated: 2026-09-23
---

# Install the Godot addon

The addon is the only part of the system that lives inside Godot. It is an
`EditorPlugin` (`@tool`) that:

- dials the server's bridge listener (`ws://127.0.0.1:9080` by default) and
  **reconnects with backoff** — launch order never matters
- routes the server's `{id, command}` envelopes to 80+ `cmd_*` handlers that
  call the Godot Editor API
- shows a **read-only status dock** (connection state, project/scene/selected
  node, recent commands with timing)
- registers the debugger plugin that powers live play-session inspection

## Option A: use the bundled project

Open the `godot/` folder of the godot-mcp checkout as a project in Godot
4.4+. Enable the plugin (**Project Settings → Plugins → godot_mcp**). This is
a minimal project that exists so the addon is loadable and testable.

## Option B: copy into your own project (typical)

```bash
cp -r godot-mcp/godot/addons/godot_mcp /path/to/your/game/addons/
```

Then **Project Settings → Plugins → godot_mcp → Enable**.

The addon checks the editor version on enable and warns below 4.4.

## Point the addon at your server

Same env var both sides — set it only if you deviate from the default:

| Setting | Default | When to set |
|---------|---------|-------------|
| `GODOT_MCP_BRIDGE_URL` | `ws://127.0.0.1:9080` | Docker, remote server, or a non-default port |

In the editor's environment (or via the project settings override), e.g. for
Docker:

```bash
GODOT_MCP_BRIDGE_URL=ws://127.0.0.1:9080 godot --path /path/to/your/game
```

## Verify

1. The **status dock** appears at the bottom of the editor (alongside
   Output/Debug): connection dot, server/Godot version, bridge URL, active
   scene, selected node, enabled toolsets, and a recent-command log with
   timing.
2. Green dot = the addon connected out to the server. The server and editor
   can start in **either** order — the addon reconnects automatically.
3. `godot_health_check()` from your agent returns
   `{"bridge_connected": true, "version": "…"}`.

## Auto-refresh for external edits (optional)

The editor's own external-file detection is **window-focus-driven** — files
changed by an agent, git, or any other tool while Godot is unfocused stay
invisible until you click into the editor. All files written *through* godot-mcp
tools already refresh the editor's filesystem view automatically; for edits made
outside the MCP path, enable the opt-in auto-refresh:

```bash
GODOT_MCP_AUTO_REFRESH=1 GODOT_MCP_AUTO_REFRESH_INTERVAL=10 godot --editor
```

The **MCP dock** (bottom panel) has an **Auto-refresh files** checkbox — the
runtime override of the env default. When on, the addon runs a periodic
`EditorFileSystem.scan()` (never stacking a scan on an in-flight one) so
external edits are picked up within one interval without focus.

Next: [configure your MCP client](getting-started-clients.md).