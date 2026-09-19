---
type: index
title: "Toolsets & tools"
description: "Every tool in the 2026.09.19 surface, grouped by toolset, with safety classes."
created: 2026-09-19
updated: 2026-09-19
---

# Toolsets & tools

184 tools across 29 categories. Only `core` + `inspection` are enabled by default; enable the rest with `godot_enable_toolset(category)`. Class meanings: [safety classes](reference-safety-classes.md).

## `analysis` — Static analysis: dependencies, signal flow, unused resources, circular deps, scene integrity.

9 tools.

| Tool | Class |
|------|-------|
| `analyze_dependencies` | read_only |
| `analyze_signal_flow` | read_only |
| `cross_scene_find_refs` | read_only |
| `detect_circular_dependencies` | read_only |
| `find_orphaned_resources` | read_only |
| `find_unused_resources` | read_only |
| `project_stats` | read_only |
| `project_structure` | read_only |
| `validate_scene_integrity` | read_only |

## `animation` — AnimationPlayers and AnimationTrees: author animations, tracks, keyframes, state machines.

8 tools.

| Tool | Class |
|------|-------|
| `add_animation_track` | mutating |
| `add_state_machine_state` | mutating |
| `create_animation` | mutating |
| `create_animation_tree` | mutating |
| `get_animation` | read_only |
| `insert_keyframe` | mutating |
| `list_animations` | read_only |
| `set_blend_tree_node` | mutating |

## `asset_import` — Import external assets (.png/.glb/.wav/…), create materials from textures, poll import status.

3 tools.

| Tool | Class |
|------|-------|
| `create_material_from_textures` | mutating |
| `get_import_status` | read_only |
| `import_asset` | mutating |

## `audio` — Audio players and AudioServer buses: add players, route buses, effects — with a verifiable layout read.

6 tools.

| Tool | Class |
|------|-------|
| `add_audio_bus` | mutating |
| `add_audio_bus_effect` | mutating |
| `add_audio_player` | mutating |
| `get_audio_bus_layout` | read_only |
| `remove_audio_bus` | destructive |
| `remove_audio_bus_effect` | destructive |

## `batch` — Bulk operations: find nodes by type, batch property sets, cross-scene edits, dependency analysis.

4 tools.

| Tool | Class |
|------|-------|
| `batch_set_property` | mutating |
| `cross_scene_set_property` | mutating |
| `find_nodes_by_type` | read_only |
| `get_dependencies` | read_only |

## `composite` — Macro round-trips: N editor commands in one bridge call, batch node creation, apply_node_edits.

4 tools.

| Tool | Class |
|------|-------|
| `apply_node_edits` | mutating |
| `batch_create_nodes` | mutating |
| `compose_node` | mutating |
| `run_commands` | mutating |

## `core` — Always-on: diagnostics, toolset management, undo, the debug_workflow recipe.

9 tools.

| Tool | Class |
|------|-------|
| `debug_workflow` | read_only |
| `disable_toolset` | read_only |
| `enable_toolset` | read_only |
| `get_server_info` | read_only |
| `health_check` | read_only |
| `list_tools_by_safety_class` | read_only |
| `list_toolsets` | read_only |
| `read_resource` | read_only |
| `undo` | mutating |

## `debugger` — Breakpoints, force_break, stack frames/variables, expression evaluation, stepping.

11 tools.

| Tool | Class |
|------|-------|
| `clear_breakpoints` | runtime |
| `continue_execution` | runtime |
| `evaluate_expression` | runtime |
| `force_break` | runtime |
| `get_frame_variables` | runtime |
| `get_stack_frames` | runtime |
| `remove_breakpoint` | runtime |
| `set_breakpoint` | runtime |
| `step_into` | runtime |
| `step_out` | runtime |
| `step_over` | runtime |

## `editor` — Editor screenshots (base64 PNG) for vision-capable clients.

1 tools.

| Tool | Class |
|------|-------|
| `capture_editor_screenshot` | read_only |

## `export` — Export presets and headless export runs.

3 tools.

| Tool | Class |
|------|-------|
| `export_project` | runtime |
| `get_export_info` | read_only |
| `list_export_presets` | read_only |

## `input` — Input simulation and recording for a live play session.

7 tools.

| Tool | Class |
|------|-------|
| `get_input_stats` | read_only |
| `play_input_sequence` | runtime |
| `record_input` | runtime |
| `simulate_action` | runtime |
| `simulate_key` | runtime |
| `simulate_mouse` | runtime |
| `stop_recording` | read_only |

## `input_map` — Input Map actions in project settings: add/remove actions and events.

5 tools.

| Tool | Class |
|------|-------|
| `add_input_action` | mutating |
| `add_input_event` | mutating |
| `clear_input_action_events` | destructive |
| `get_input_action_events` | read_only |
| `remove_input_action` | destructive |

## `inspection` — Read-only project/scene/node inspection.

9 tools.

| Tool | Class |
|------|-------|
| `get_active_scene` | read_only |
| `get_node_groups` | read_only |
| `get_node_properties` | read_only |
| `get_node_property` | read_only |
| `get_node_property_list` | read_only |
| `get_project_info` | read_only |
| `get_scene_tree` | read_only |
| `get_selected_node` | read_only |
| `list_scenes` | read_only |

## `navigation` — NavigationRegion/Agent setup, navmesh baking, navigation layers.

5 tools.

| Tool | Class |
|------|-------|
| `bake_navigation_mesh` | mutating |
| `get_navigation_region` | read_only |
| `set_navigation_layers` | mutating |
| `setup_navigation_agent` | mutating |
| `setup_navigation_region` | mutating |

## `particles` — GPUParticles2D/3D: create, configure materials, presets, color gradients.

5 tools.

| Tool | Class |
|------|-------|
| `apply_particle_preset` | mutating |
| `create_particles` | mutating |
| `get_particle_material` | read_only |
| `set_particle_color_gradient` | mutating |
| `set_particle_material` | mutating |

## `physics` — Physics bodies, collision shapes, raycasts, layer/mask management.

4 tools.

| Tool | Class |
|------|-------|
| `add_raycast` | mutating |
| `set_physics_layers` | mutating |
| `setup_collision` | mutating |
| `setup_physics_body` | mutating |

## `profiling` — Editor + running-game performance monitors (FPS, draw calls, memory).

2 tools.

| Tool | Class |
|------|-------|
| `get_editor_performance` | read_only |
| `get_performance_monitors` | read_only |

## `project` — Filesystem tree, file search, project settings, UID resolution.

6 tools.

| Tool | Class |
|------|-------|
| `delete_resource_file` | destructive |
| `get_filesystem_tree` | read_only |
| `get_setting` | read_only |
| `resolve_uid` | read_only |
| `search_files` | read_only |
| `set_setting` | mutating |

## `project_scaffold` — Scaffold a new project skeleton (directories, base scenes).

1 tools.

| Tool | Class |
|------|-------|
| `scaffold_project` | destructive |

## `resources_edit` — Author .tres resource files, register/unregister autoloads.

5 tools.

| Tool | Class |
|------|-------|
| `create_resource` | mutating |
| `read_resource_file` | read_only |
| `register_autoload` | mutating |
| `set_resource_property` | mutating |
| `unregister_autoload` | mutating |

## `runtime` — Headless run + output capture; live play session lifecycle.

9 tools.

| Tool | Class |
|------|-------|
| `capture_game_screenshot` | read_only |
| `find_ui_elements` | read_only |
| `get_game_scene_tree` | read_only |
| `get_property_samples` | read_only |
| `is_playing` | read_only |
| `monitor_property` | read_only |
| `play_scene` | runtime |
| `run_and_capture` | runtime |
| `stop_scene` | runtime |

## `scene_3d` — 3D scenes: meshes, cameras, lights, environments, GridMaps, MeshLibraries.

8 tools.

| Tool | Class |
|------|-------|
| `add_mesh_instance` | mutating |
| `add_mesh_library_item` | mutating |
| `create_mesh_library` | mutating |
| `gridmap_get_cell` | read_only |
| `gridmap_set_cell` | mutating |
| `setup_camera` | mutating |
| `setup_environment` | mutating |
| `setup_lighting` | mutating |

## `scene_edit` — Create/modify/delete nodes, scripts, signals, scenes — the core authoring surface.

23 tools.

| Tool | Class |
|------|-------|
| `add_to_group` | mutating |
| `attach_script` | mutating |
| `close_scene` | destructive |
| `connect_signal` | mutating |
| `create_node` | mutating |
| `create_scene` | mutating |
| `delete_node` | destructive |
| `disconnect_signal` | mutating |
| `duplicate_node` | mutating |
| `instance_scene` | mutating |
| `list_open_scenes` | read_only |
| `list_signal_connections` | read_only |
| `move_node` | mutating |
| `open_scene` | mutating |
| `reload_scene` | destructive |
| `remove_from_group` | mutating |
| `rename_node` | mutating |
| `rescan_filesystem` | read_only |
| `save_all_scenes` | mutating |
| `save_scene` | mutating |
| `select_nodes` | mutating |
| `set_editable_children` | mutating |
| `set_node_property` | mutating |

## `scripts` — Read/write/patch GDScript; parse checks.

6 tools.

| Tool | Class |
|------|-------|
| `get_parse_errors` | read_only |
| `get_script_for_node` | read_only |
| `list_scripts` | read_only |
| `patch_script` | mutating |
| `read_script` | read_only |
| `write_script` | mutating |

## `shader` — Author .gdshader files, assign materials, set/verify uniform params, compile-validate.

6 tools.

| Tool | Class |
|------|-------|
| `assign_shader_material` | mutating |
| `create_shader` | mutating |
| `get_shader_param` | read_only |
| `read_shader` | read_only |
| `set_shader_param` | mutating |
| `validate_shader` | read_only |

## `testing` — Assertions, test scenarios, stress fuzz, screenshot diffing.

5 tools.

| Tool | Class |
|------|-------|
| `assert_node_state` | read_only |
| `compare_screenshots` | read_only |
| `run_stress_test` | runtime |
| `run_test_scenario` | runtime |
| `run_tests` | runtime |

## `theme_ui` — Theme authoring: create themes, set colors/fonts/styleboxes, UI element styling.

5 tools.

| Tool | Class |
|------|-------|
| `create_theme` | mutating |
| `get_node_theme_overrides` | read_only |
| `set_theme_color` | mutating |
| `set_theme_font_size` | mutating |
| `set_theme_stylebox` | mutating |

## `tilemap` — TileMapLayers: create, set cells, fill rects, TileSet authoring.

9 tools.

| Tool | Class |
|------|-------|
| `add_tileset_atlas_source` | mutating |
| `create_tile` | mutating |
| `create_tileset` | mutating |
| `tilemap_clear` | mutating |
| `tilemap_fill_rect` | mutating |
| `tilemap_get_cell` | read_only |
| `tilemap_get_used_cells` | read_only |
| `tilemap_layers` | read_only |
| `tilemap_set_cell` | mutating |

## `visual_shader` — VisualShader graphs: nodes, connections, constants.

6 tools.

| Tool | Class |
|------|-------|
| `add_shader_node` | mutating |
| `connect_shader_nodes` | mutating |
| `create_visual_shader` | mutating |
| `list_shader_node_types` | read_only |
| `read_visual_shader` | read_only |
| `set_shader_node_param` | mutating |
