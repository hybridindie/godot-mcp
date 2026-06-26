---
name: godot-mcp-getting-started
description: Connect to and drive a Godot editor through the godot-mcp server. Use at the start of any Godot task via godot-mcp — it teaches the toolset-gating model (enable a toolset before its tools exist), the dry_run/confirm safety convention, and how to verify the bridge. Triggers on "use godot-mcp", "drive Godot", "control the Godot editor", "godot-mcp tools aren't showing up", "unknown tool from godot", "set up godot-mcp".
---

# godot-mcp: getting started

godot-mcp exposes the Godot editor (inspection, scene edits, scripts, runtime) over MCP. Tools are named `godot_<toolset>_<action>`. Read this once at the start of a Godot session — it prevents the two most common failures: missing tools and unconfirmed destructive edits.

## 1. Confirm the bridge is up

The server talks to a running Godot editor over a WebSocket bridge. If Godot isn't open with the addon enabled, every editor tool fails.

```
godot_health_check()      # bridge connected? which URL?
godot_get_server_info()   # toolsets, active scene, next_steps, common errors
```

If disconnected: open the `godot/` project in Godot 4.4+, enable the plugin (Project Settings → Plugins → godot_mcp), and check the status dock.

## 2. Toolsets are gated — enable before you use

Only `core` (diagnostics/toolset management) and `inspection` (read-only reading) are on by default. **Every other capability is hidden until you enable it.** Calling a hidden tool returns `ToolError: unknown tool` — there is no fallback.

```
godot_list_toolsets()                 # what exists / what's enabled
godot_enable_toolset('scene_edit')    # turn on what you need, then call its tools
```

Quick map: edit scenes → `scene_edit` · scripts → `scripts` · live play → `runtime` (+ `input`) · debug breakpoints → `debugger` (+ `runtime`) · physics → `physics` · autoloads/resources → `resources_edit` · export → `export` · many-node changes → `batch`.

## 3. The safety convention

- **Read-only** tools never mutate — no flags needed.
- **Mutating** tools accept `dry_run=True` — they report what *would* change and do nothing. Preview when unsure.
- **Destructive** tools (delete/overwrite, e.g. `godot_scene_edit_delete_node`) require `confirm=True` or they refuse; they also support `dry_run`.

## 4. Use the built-in workflow prompts

The server ships step-by-step recipes as MCP prompts (slash commands like `/mcp__godot-mcp__build_scene`): `toolset_discovery`, `build_scene`, `play_test`, `script_edit`, `debug_scene`, `troubleshoot`. Reach for them, or use the companion skills `godot-mcp-build-a-scene` and `godot-mcp-playtest-and-debug`.

## When something fails

- `unknown tool` → the toolset isn't enabled (step 2), or you mixed up a server-side tool with an editor tool.
- `PRECONDITION_FAILED` → read `required`: `active_scene` (open a scene), `confirm` (add `confirm=True`), `bridge_connected` (step 1).
- Run `godot_get_server_info()` first — its `next_steps` field usually names the fix.
