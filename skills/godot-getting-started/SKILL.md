---
name: godot-getting-started
description: Connect to and drive a Godot editor through the godot-mcp server. Use at the start of any Godot task via godot-mcp — it teaches the version check, the toolset-gating model (enable a toolset before its tools exist), the dry_run/confirm safety convention, and how to verify the bridge. Triggers on "use godot-mcp", "drive Godot", "control the Godot editor", "godot-mcp tools aren't showing up", "unknown tool from godot", "set up godot-mcp".
---

# godot: getting started

godot-mcp exposes the Godot editor (inspection, scene edits, scripts, runtime) over MCP. This skill documents the **2026.09.02** surface — 180 tools, 29 categories. Tools are named `godot_<toolset>_<action>`. Read this once at the start of a Godot session — it prevents the three most common failures: a version mismatch, missing tools, and unconfirmed destructive edits.

## 1. Confirm the bridge and the version

The server talks to a running Godot editor over a WebSocket bridge. If Godot isn't open with the addon enabled, every editor tool fails.

```
godot_health_check()      # bridge connected? which URL? → also returns version
godot_get_server_info()   # version, contract_version, toolsets, active scene, next_steps
```

- `godot_health_check()` returns `version` — if it isn't **2026.09.02**, this skill may be stale; rely on `godot_get_server_info()`'s toolset/tool inventory instead of the counts here.
- `godot_get_server_info()` returns `contract_version` (tool-surface compatibility, currently 1) — a client is compatible when `min_compatible_contract <= yours <= contract_version`.
- If disconnected: open the `godot/` project in Godot 4.4+ (validated on 4.7), enable the plugin (Project Settings → Plugins → godot_mcp), and check the status dock.

## 2. Toolsets are gated — enable before you use

Only `core` (always on) and `inspection` (read-only) are enabled by default. **Every other capability is hidden until you enable it.** Calling a hidden tool returns `unknown tool` — there is no fallback. Some toolsets require Godot 4.4+ (`scene_edit`, `input_map`, `tilemap`, `scene_3d`); `godot_list_toolsets()` reports `min_godot` per toolset.

```
godot_list_toolsets()                 # what exists / what's enabled / min Godot
godot_enable_toolset('scene_edit')    # turn on what you need, then call its tools
```

Quick map (all 28 gated toolsets):

- **Scene building** — edit nodes/scenes/signals → `scene_edit` · macro edits in one round-trip → `composite` · 3D scenes (meshes, cameras, lights, GridMap) → `scene_3d` · UI themes → `theme_ui` · tilemaps → `tilemap` · particles → `particles` · navigation → `navigation` · physics → `physics` · animation → `animation` · audio buses → `audio` · shaders → `shader` · visual shader graphs → `visual_shader`
- **Code & data** — GDScript files → `scripts` · resources (.tres) + autoloads → `resources_edit` · project files/settings/UIDs → `project` · new project skeleton → `project_scaffold`
- **Run & verify** — headless run + output capture → `runtime` · live play-test + input sim → `input` · input actions in project settings → `input_map` · automated assertions/screenshots → `testing` · breakpoints/stepping → `debugger` · performance monitors → `profiling`
- **Bulk & ship** — batch/cross-scene ops → `batch` · static analysis → `analysis` · export presets → `export` · import external assets → `asset_import` · editor screenshots (vision clients) → `editor`

Always-on `core` extras: `godot_undo` (undo the last editor action), `godot_list_tools_by_safety_class()`, `godot_debug_workflow()` (diagnostics recipe), the toolset tools, and the two checks above.

## 3. The safety convention

- **Read-only** tools never mutate — no flags needed.
- **Mutating** tools accept `dry_run=True` — they report what *would* change and do nothing. Preview when unsure.
- **Destructive** tools (delete/overwrite, e.g. `godot_scene_edit_delete_node`) require `confirm=True` or they refuse; they also support `dry_run`.
- **Runtime** tools control game execution (play/stop/breakpoints) — no `dry_run`.

## 4. Use the built-in workflow prompts

The server ships step-by-step recipes as MCP prompts (slash commands like `/mcp__godot-mcp__build_scene`): `toolset_discovery`, `build_scene`, `play_test`, `script_edit`, `debug_scene`, `troubleshoot`, `author_resource`, `export_build`, `batch_refactor`. Reach for them, or use the companion skills `godot-playtest-and-debug` and `godot-expert`.

## When something fails

- `unknown tool` → the toolset isn't enabled (step 2), or you mixed up a server-side tool with an editor tool.
- `PRECONDITION_FAILED` → read `required`: `active_scene` (open a scene), `confirm` (add `confirm=True`), `bridge_connected` (step 1).
- Run `godot_get_server_info()` first — its `next_steps` field usually names the fix.