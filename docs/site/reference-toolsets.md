---
type: index
title: "Toolsets & tools"
description: "Every tool in the 193-tool surface, grouped by toolset, with safety classes."
created: 2026-09-19
updated: 2026-09-28
---

# Toolsets & tools

193 tools across 29 categories. Only `core` + `inspection` are enabled by default; enable the rest with `godot_enable_toolset(category)`. Class meanings: [safety classes](reference-safety-classes.md).

## `analysis` — Static analysis: dependencies, signal flow, unused resources, circular deps, scene integrity.

9 tools.

| Tool | Class |
|------|-------|
| `godot_analysis_analyze_dependencies` | read_only |
| `godot_analysis_analyze_signal_flow` | read_only |
| `godot_analysis_cross_scene_find_refs` | read_only |
| `godot_analysis_detect_circular_dependencies` | read_only |
| `godot_analysis_find_orphaned_resources` | read_only |
| `godot_analysis_find_unused_resources` | read_only |
| `godot_analysis_project_stats` | read_only |
| `godot_analysis_project_structure` | read_only |
| `godot_analysis_validate_scene_integrity` | read_only |

## `animation` — AnimationPlayers and AnimationTrees: author animations, tracks, keyframes, state machines.

8 tools.

| Tool | Class |
|------|-------|
| `godot_animation_add_state_machine_state` | mutating |
| `godot_animation_add_track` | mutating |
| `godot_animation_create` | mutating |
| `godot_animation_create_tree` | mutating |
| `godot_animation_get` | read_only |
| `godot_animation_insert_keyframe` | mutating |
| `godot_animation_list_animations` | read_only |
| `godot_animation_set_blend_tree_node` | mutating |

## `asset_import` — Import external assets (.png/.glb/.wav/…), create materials from textures, poll import status.

3 tools.

| Tool | Class |
|------|-------|
| `godot_asset_import_asset` | mutating |
| `godot_asset_import_create_material_from_textures` | mutating |
| `godot_asset_import_get_status` | read_only |

## `audio` — Audio players and AudioServer buses: add players, route buses, effects — with a verifiable layout read.

6 tools.

| Tool | Class |
|------|-------|
| `godot_audio_add_bus` | mutating |
| `godot_audio_add_bus_effect` | mutating |
| `godot_audio_add_player` | mutating |
| `godot_audio_get_bus_layout` | read_only |
| `godot_audio_remove_bus` | destructive |
| `godot_audio_remove_bus_effect` | destructive |

## `batch` — Bulk operations: find nodes by type, batch property sets, cross-scene edits, dependency analysis.

4 tools.

| Tool | Class |
|------|-------|
| `godot_batch_cross_scene_set_property` | mutating |
| `godot_batch_find_nodes_by_type` | read_only |
| `godot_batch_get_dependencies` | read_only |
| `godot_batch_set_property` | mutating |

## `composite` — Macro round-trips: N editor commands in one bridge call, batch node creation, apply_node_edits.

4 tools.

| Tool | Class |
|------|-------|
| `godot_composite_apply_node_edits` | mutating |
| `godot_composite_batch_create_nodes` | mutating |
| `godot_composite_compose_node` | mutating |
| `godot_composite_run_commands` | mutating |

## `core` — Always-on: diagnostics, toolset management, undo, the debug_workflow recipe.

12 tools.

| Tool | Class |
|------|-------|
| `godot_debug_workflow` | read_only |
| `godot_describe_class` | read_only |
| `godot_disable_toolset` | read_only |
| `godot_enable_toolset` | read_only |
| `godot_get_server_info` | read_only |
| `godot_health_check` | read_only |
| `godot_list_history` | read_only |
| `godot_list_tools_by_safety_class` | read_only |
| `godot_list_toolsets` | read_only |
| `godot_read_resource` | read_only |
| `godot_redo` | mutating |
| `godot_undo` | mutating |

## `debugger` — Breakpoints, force_break, stack frames/variables, expression evaluation, stepping.

11 tools.

| Tool | Class |
|------|-------|
| `godot_debugger_clear_breakpoints` | runtime |
| `godot_debugger_continue_execution` | runtime |
| `godot_debugger_evaluate_expression` | runtime |
| `godot_debugger_force_break` | runtime |
| `godot_debugger_get_frame_variables` | runtime |
| `godot_debugger_get_stack_frames` | runtime |
| `godot_debugger_remove_breakpoint` | runtime |
| `godot_debugger_set_breakpoint` | runtime |
| `godot_debugger_step_into` | runtime |
| `godot_debugger_step_out` | runtime |
| `godot_debugger_step_over` | runtime |

## `editor` — Editor screenshots (base64 PNG) for vision-capable clients.

1 tools.

| Tool | Class |
|------|-------|
| `godot_editor_capture_screenshot` | read_only |

## `export` — Export presets and headless export runs.

3 tools.

| Tool | Class |
|------|-------|
| `godot_export_get_info` | read_only |
| `godot_export_list_presets` | read_only |
| `godot_export_project` | runtime |

## `input` — Input simulation and recording for a live play session.

7 tools.

| Tool | Class |
|------|-------|
| `godot_input_get_stats` | read_only |
| `godot_input_play_sequence` | runtime |
| `godot_input_record` | runtime |
| `godot_input_simulate_action` | runtime |
| `godot_input_simulate_key` | runtime |
| `godot_input_simulate_mouse` | runtime |
| `godot_input_stop_recording` | read_only |

## `input_map` — Input Map actions in project settings: add/remove actions and events.

5 tools.

| Tool | Class |
|------|-------|
| `godot_input_map_add_action` | mutating |
| `godot_input_map_add_event` | mutating |
| `godot_input_map_clear_action_events` | destructive |
| `godot_input_map_get_action_events` | read_only |
| `godot_input_map_remove_action` | destructive |

## `inspection` — Read-only project/scene/node inspection.

11 tools.

| Tool | Class |
|------|-------|
| `godot_inspection_diff_snapshots` | read_only |
| `godot_inspection_get_active_scene` | read_only |
| `godot_inspection_get_node_groups` | read_only |
| `godot_inspection_get_node_properties` | read_only |
| `godot_inspection_get_node_property` | read_only |
| `godot_inspection_get_node_property_list` | read_only |
| `godot_inspection_get_project_info` | read_only |
| `godot_inspection_get_scene_tree` | read_only |
| `godot_inspection_get_selected_node` | read_only |
| `godot_inspection_list_scenes` | read_only |
| `godot_inspection_snapshot_subtree` | read_only |

## `navigation` — NavigationRegion/Agent setup, navmesh baking, navigation layers.

5 tools.

| Tool | Class |
|------|-------|
| `godot_navigation_bake_mesh` | mutating |
| `godot_navigation_get_region` | read_only |
| `godot_navigation_set_layers` | mutating |
| `godot_navigation_setup_agent` | mutating |
| `godot_navigation_setup_region` | mutating |

## `particles` — GPUParticles2D/3D: create, configure materials, presets, color gradients.

5 tools.

| Tool | Class |
|------|-------|
| `godot_particles_apply_preset` | mutating |
| `godot_particles_create` | mutating |
| `godot_particles_get_material` | read_only |
| `godot_particles_set_color_gradient` | mutating |
| `godot_particles_set_material` | mutating |

## `physics` — Physics bodies, collision shapes, raycasts, layer/mask management.

4 tools.

| Tool | Class |
|------|-------|
| `godot_physics_add_raycast` | mutating |
| `godot_physics_set_layers` | mutating |
| `godot_physics_setup_body` | mutating |
| `godot_physics_setup_collision` | mutating |

## `profiling` — Editor + running-game performance monitors (FPS, draw calls, memory).

2 tools.

| Tool | Class |
|------|-------|
| `godot_profiling_get_editor_performance` | read_only |
| `godot_profiling_get_performance_monitors` | read_only |

## `project` — Filesystem tree, file search, project settings, UID resolution.

7 tools.

| Tool | Class |
|------|-------|
| `godot_project_delete_resource_file` | destructive |
| `godot_project_get_filesystem_tree` | read_only |
| `godot_project_get_setting` | read_only |
| `godot_project_move_file` | mutating |
| `godot_project_resolve_uid` | read_only |
| `godot_project_search_files` | read_only |
| `godot_project_set_setting` | mutating |

## `project_scaffold` — Scaffold a new project skeleton (directories, base scenes).

1 tools.

| Tool | Class |
|------|-------|
| `godot_project_scaffold` | destructive |

## `resources_edit` — Author .tres resource files, register/unregister autoloads.

5 tools.

| Tool | Class |
|------|-------|
| `godot_resources_edit_create_resource` | mutating |
| `godot_resources_edit_read_resource_file` | read_only |
| `godot_resources_edit_register_autoload` | mutating |
| `godot_resources_edit_set_resource_property` | mutating |
| `godot_resources_edit_unregister_autoload` | mutating |

## `runtime` — Headless run + output capture; live play session lifecycle.

11 tools.

| Tool | Class |
|------|-------|
| `godot_runtime_capture_game_screenshot` | read_only |
| `godot_runtime_find_ui_elements` | read_only |
| `godot_runtime_get_game_output` | read_only |
| `godot_runtime_get_game_scene_tree` | read_only |
| `godot_runtime_get_property_samples` | read_only |
| `godot_runtime_is_playing` | read_only |
| `godot_runtime_monitor_property` | read_only |
| `godot_runtime_play_scene` | runtime |
| `godot_runtime_read_property` | read_only |
| `godot_runtime_run_and_capture` | runtime |
| `godot_runtime_stop_scene` | runtime |

## `scene_3d` — 3D scenes: meshes, cameras, lights, environments, GridMaps, MeshLibraries.

8 tools.

| Tool | Class |
|------|-------|
| `godot_scene_3d_add_mesh_instance` | mutating |
| `godot_scene_3d_add_mesh_library_item` | mutating |
| `godot_scene_3d_create_mesh_library` | mutating |
| `godot_scene_3d_gridmap_get_cell` | read_only |
| `godot_scene_3d_gridmap_set_cell` | mutating |
| `godot_scene_3d_setup_camera` | mutating |
| `godot_scene_3d_setup_environment` | mutating |
| `godot_scene_3d_setup_lighting` | mutating |

## `scene_edit` — Create/modify/delete nodes, scripts, signals, scenes — the core authoring surface.

24 tools.

| Tool | Class |
|------|-------|
| `godot_scene_edit_add_to_group` | mutating |
| `godot_scene_edit_attach_script` | mutating |
| `godot_scene_edit_close_scene` | destructive |
| `godot_scene_edit_connect_signal` | mutating |
| `godot_scene_edit_create_node` | mutating |
| `godot_scene_edit_create_scene` | mutating |
| `godot_scene_edit_delete_node` | destructive |
| `godot_scene_edit_disconnect_signal` | mutating |
| `godot_scene_edit_duplicate_node` | mutating |
| `godot_scene_edit_extract_scene` | mutating |
| `godot_scene_edit_instance_scene` | mutating |
| `godot_scene_edit_list_open_scenes` | read_only |
| `godot_scene_edit_list_signal_connections` | read_only |
| `godot_scene_edit_move_node` | mutating |
| `godot_scene_edit_open_scene` | mutating |
| `godot_scene_edit_reload_scene` | destructive |
| `godot_scene_edit_remove_from_group` | mutating |
| `godot_scene_edit_rename_node` | mutating |
| `godot_scene_edit_rescan_filesystem` | read_only |
| `godot_scene_edit_save_all_scenes` | mutating |
| `godot_scene_edit_save_scene` | mutating |
| `godot_scene_edit_select_nodes` | mutating |
| `godot_scene_edit_set_editable_children` | mutating |
| `godot_scene_edit_set_node_property` | mutating |

## `scripts` — Read/write/patch GDScript; parse checks.

6 tools.

| Tool | Class |
|------|-------|
| `godot_scripts_get_for_node` | read_only |
| `godot_scripts_get_parse_errors` | read_only |
| `godot_scripts_list` | read_only |
| `godot_scripts_patch` | mutating |
| `godot_scripts_read` | read_only |
| `godot_scripts_write` | mutating |

## `shader` — Author .gdshader files, assign materials, set/verify uniform params, compile-validate.

6 tools.

| Tool | Class |
|------|-------|
| `godot_shader_assign_material` | mutating |
| `godot_shader_create` | mutating |
| `godot_shader_get_param` | read_only |
| `godot_shader_read` | read_only |
| `godot_shader_set_param` | mutating |
| `godot_shader_validate` | read_only |

## `testing` — Assertions, test scenarios, stress fuzz, screenshot diffing.

5 tools.

| Tool | Class |
|------|-------|
| `godot_testing_assert_node_state` | read_only |
| `godot_testing_compare_screenshots` | read_only |
| `godot_testing_run_stress_test` | runtime |
| `godot_testing_run_test_scenario` | runtime |
| `godot_testing_run_tests` | runtime |

## `theme_ui` — Theme authoring: create themes, set colors/fonts/styleboxes, UI element styling.

5 tools.

| Tool | Class |
|------|-------|
| `godot_theme_ui_create` | mutating |
| `godot_theme_ui_get_node_overrides` | read_only |
| `godot_theme_ui_set_color` | mutating |
| `godot_theme_ui_set_font_size` | mutating |
| `godot_theme_ui_set_stylebox` | mutating |

## `tilemap` — TileMapLayers: create, set cells, fill rects, TileSet authoring.

9 tools.

| Tool | Class |
|------|-------|
| `godot_tilemap_add_tileset_atlas_source` | mutating |
| `godot_tilemap_clear` | mutating |
| `godot_tilemap_create_tile` | mutating |
| `godot_tilemap_create_tileset` | mutating |
| `godot_tilemap_fill_rect` | mutating |
| `godot_tilemap_get_cell` | read_only |
| `godot_tilemap_get_used_cells` | read_only |
| `godot_tilemap_layers` | read_only |
| `godot_tilemap_set_cell` | mutating |

## `visual_shader` — VisualShader graphs: nodes, connections, constants.

6 tools.

| Tool | Class |
|------|-------|
| `godot_visual_shader_add_node` | mutating |
| `godot_visual_shader_connect_nodes` | mutating |
| `godot_visual_shader_create` | mutating |
| `godot_visual_shader_list_node_types` | read_only |
| `godot_visual_shader_read` | read_only |
| `godot_visual_shader_set_node_param` | mutating |
