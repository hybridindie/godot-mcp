---
type: index
title: "Prompts & resources"
description: "The 9 workflow prompts and the 4 godot:// read-only resources — the surfaces beyond tools."
created: 2026-09-19
updated: 2026-09-19
---

# Prompts & resources

Beyond the 184 tools, the server exposes two more MCP surfaces: **prompts**
(step-numbered workflow templates the agent renders for guidance) and
**resources** (read-only `godot://` snapshots the host can fetch).

## Workflow prompts (9)

Prompts are recipes, not actions: each one is a step-numbered template naming
*which tools to call in what order*. Clients that surface prompts show them as
slash commands (e.g. `/mcp__godot-mcp__build_scene`). Render with
`list_prompts()` / `render_prompt(name, arguments)`.

| Prompt | Purpose | Key tools it orchestrates |
|--------|---------|---------------------------|
| `toolset_discovery` | The gating protocol — **use first in every session**; teaches enable-before-use | `godot_get_server_info`, `godot_enable_toolset`, representative gated tools |
| `build_scene` | Create a scene end-to-end: nodes, scripts, collision | `create_scene`, `create_node`, `attach_script`, `physics_setup_collision` |
| `play_test` | Live play-testing: probe autoload, play, inspect, simulate input | `play_scene`, `input_simulate_*`, `runtime_find_ui_elements` |
| `script_edit` | Author GDScript: write, attach, parse-check, patch | `scripts_write`, `scripts_patch`, `scripts_get_parse_errors` |
| `debug_scene` | Systematic debugging: health → workflow → signal flow → unused resources | `godot_debug_workflow`, `analysis_*`, `get_node_properties` |
| `troubleshoot` | Diagnostic playbook for common failures (bridge, toolsets, probe) | `godot_health_check`, `get_server_info`, `list_toolsets` |
| `author_resource` | Author a resource (.tres/tileset) with the right toolset | `tilemap_create_tileset`, `add_tileset_atlas_source`, `create_tile` |
| `export_build` | Ship a build: presets → export → verify | `export_list_presets`, `export_get_info`, `export_project` |
| `batch_refactor` | Safe bulk property changes: find → preview → apply | `batch_find_nodes_by_type`, `batch_set_property`, `cross_scene_set_property` |

Every prompt composes from the shared toolset-protocol text (single source of
truth in `mcp_server/toolset_protocol.py`), so the gating instructions cannot
drift between the server instructions and the prompts.

## Read-only resources (4)

Resources are addressable, refreshed-on-access snapshots — JSON strings, no
side effects ever (mutations always go through tools). On a bridge failure the
resource returns valid JSON carrying the structured error. Clients without
resource support can read them through the `read_resource` fallback tool.

| URI | Returns |
|-----|---------|
| `godot://project/info` | Project metadata: name, Godot version, main scene, autoloads, input actions |
| `godot://scene/current` | The currently open scene: `is_open`, `path`, `name` |
| `godot://scene/tree` | The full active scene tree `{name, type, script, children}` (may be large) |
| `godot://node/selected` | The currently selected node snapshot, or `{"selected": null}` |

These mirror the always-on inspection tools (`get_project_info`,
`get_active_scene`, `get_scene_tree`, `get_selected_node`) — read-only context
is exposed both ways by design; which one a client uses depends on whether it
implements the resource protocol.

## Discovery

Both surfaces appear in `godot_get_server_info` (`prompts[]`) and via the
standard MCP `prompts/list` and `resources/list` calls.
