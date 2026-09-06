"""Bare-name resolution and param translation for ``run_commands`` (#420, #421).

``godot_composite_run_commands`` accepts sub-commands in three forms: the addon
command (``cmd_set_physics_layers``), the bare action name of an *untrimmed*
tool (``set_node_property``), and — the gap this module closes — the bare
exposed name of a tool whose action the ``godot_`` transform trimmed or
reordered (``set_layers`` → ``cmd_set_physics_layers``, ``add_bus`` →
``cmd_add_audio_bus``).

The table below is static and mirrors the tool registry: ``BARE_TO_COMMAND``
is derived from the same ``godot_tool_name``/handler data the tool surface is
registered with (see tests/unit/test_command_map.py, which cross-checks it
against the live registry so it cannot drift). Params are passed through
verbatim except where a tool's Python signature renames the addon's key —
currently only ``node_name`` → ``name`` (create/compose).
"""

from __future__ import annotations

from typing import Any

# Exposed bare name (exposed tool name minus the ``godot_`` prefix) -> the addon
# command the tool actually routes to. Single-bridge-command tools only:
# multi-step orchestrators (run_test_scenario, run_stress_test, run_tests,
# export_project, debug_workflow) run several commands with interleaved logic
# and cannot be expressed as one batch entry.
BARE_TO_COMMAND: dict[str, str] = {
    "animation_add_state_machine_state": "cmd_add_state_machine_state",
    "animation_add_track": "cmd_add_animation_track",
    "animation_create": "cmd_create_animation",
    "animation_create_tree": "cmd_create_animation_tree",
    "animation_get": "cmd_get_animation",
    "animation_insert_keyframe": "cmd_insert_keyframe",
    "animation_list_animations": "cmd_list_animations",
    "animation_set_blend_tree_node": "cmd_set_blend_tree_node",
    "asset_import_asset": "cmd_import_asset",
    "asset_import_create_material_from_textures": "cmd_create_material_from_textures",
    "asset_import_get_status": "cmd_get_import_status",
    "audio_add_bus": "cmd_add_audio_bus",
    "audio_add_bus_effect": "cmd_add_audio_bus_effect",
    "audio_add_player": "cmd_add_audio_player",
    "audio_get_bus_layout": "cmd_get_audio_bus_layout",
    "audio_remove_bus": "cmd_remove_audio_bus",
    "audio_remove_bus_effect": "cmd_remove_audio_bus_effect",
    "batch_cross_scene_set_property": "cmd_cross_scene_set_property",
    "batch_find_nodes_by_type": "cmd_find_nodes_by_type",
    "batch_get_dependencies": "cmd_get_dependencies",
    "batch_set_property": "cmd_batch_set_property",
    "composite_apply_node_edits": "cmd_apply_node_edits",
    "composite_batch_create_nodes": "cmd_batch_create_nodes",
    "composite_compose_node": "cmd_compose_node",
    "composite_run_commands": "cmd_run_commands",
    "debugger_clear_breakpoints": "cmd_clear_breakpoints",
    "debugger_continue_execution": "cmd_continue_execution",
    "debugger_evaluate_expression": "cmd_evaluate_expression",
    "debugger_force_break": "cmd_force_break",
    "debugger_get_frame_variables": "cmd_get_frame_variables",
    "debugger_get_stack_frames": "cmd_get_stack_frames",
    "debugger_remove_breakpoint": "cmd_remove_breakpoint",
    "debugger_set_breakpoint": "cmd_set_breakpoint",
    "debugger_step_into": "cmd_step_into",
    "debugger_step_out": "cmd_step_out",
    "debugger_step_over": "cmd_step_over",
    "editor_capture_screenshot": "cmd_capture_editor_screenshot",
    "export_get_info": "cmd_get_export_info",
    "export_list_presets": "cmd_list_export_presets",
    "input_get_stats": "cmd_get_input_stats",
    "input_map_add_action": "cmd_add_input_action",
    "input_map_add_event": "cmd_add_input_event",
    "input_map_clear_action_events": "cmd_clear_input_action_events",
    "input_map_get_action_events": "cmd_get_input_action_events",
    "input_map_remove_action": "cmd_remove_input_action",
    "input_play_sequence": "cmd_play_input_sequence",
    "input_record": "cmd_record_input",
    "input_simulate_action": "cmd_simulate_action",
    "input_simulate_key": "cmd_simulate_key",
    "input_simulate_mouse": "cmd_simulate_mouse",
    "input_stop_recording": "cmd_stop_recording",
    "inspection_get_active_scene": "cmd_get_active_scene",
    "inspection_get_node_groups": "cmd_get_node_groups",
    "inspection_get_node_properties": "cmd_get_node_properties",
    "inspection_get_node_property": "cmd_get_node_property",
    "inspection_get_node_property_list": "cmd_get_node_property_list",
    "inspection_get_project_info": "cmd_get_project_info",
    "inspection_get_scene_tree": "cmd_get_scene_tree",
    "inspection_get_selected_node": "cmd_get_selected_node",
    "inspection_list_scenes": "cmd_list_scenes",
    "navigation_bake_mesh": "cmd_bake_navigation_mesh",
    "navigation_get_region": "cmd_get_navigation_region",
    "navigation_set_layers": "cmd_set_navigation_layers",
    "navigation_setup_agent": "cmd_setup_navigation_agent",
    "navigation_setup_region": "cmd_setup_navigation_region",
    "particles_apply_preset": "cmd_apply_particle_preset",
    "particles_create": "cmd_create_particles",
    "particles_get_material": "cmd_get_particle_material",
    "particles_set_color_gradient": "cmd_set_particle_color_gradient",
    "particles_set_material": "cmd_set_particle_material",
    "physics_add_raycast": "cmd_add_raycast",
    "physics_set_layers": "cmd_set_physics_layers",
    "physics_setup_body": "cmd_setup_physics_body",
    "physics_setup_collision": "cmd_setup_collision",
    "profiling_get_editor_performance": "cmd_get_editor_performance",
    "profiling_get_performance_monitors": "cmd_get_performance_monitors",
    "project_delete_resource_file": "cmd_delete_resource_file",
    "project_get_filesystem_tree": "cmd_get_filesystem_tree",
    "project_get_setting": "cmd_get_setting",
    "project_resolve_uid": "cmd_uid_to_path",
    "project_scaffold": "cmd_scaffold_project",
    "project_search_files": "cmd_search_files",
    "project_set_setting": "cmd_set_setting",
    "resources_edit_create_resource": "cmd_create_resource",
    "resources_edit_read_resource_file": "cmd_read_resource",
    "resources_edit_register_autoload": "cmd_register_autoload",
    "resources_edit_set_resource_property": "cmd_set_resource_property",
    "resources_edit_unregister_autoload": "cmd_unregister_autoload",
    "runtime_find_ui_elements": "cmd_find_ui_elements",
    "runtime_get_game_scene_tree": "cmd_get_game_scene_tree",
    "runtime_get_property_samples": "cmd_get_property_samples",
    "runtime_is_playing": "cmd_is_playing",
    "runtime_monitor_property": "cmd_monitor_property",
    "runtime_play_scene": "cmd_play_scene",
    "runtime_stop_scene": "cmd_stop_scene",
    "scene_3d_add_mesh_instance": "cmd_add_mesh_instance",
    "scene_3d_add_mesh_library_item": "cmd_add_mesh_library_item",
    "scene_3d_create_mesh_library": "cmd_create_mesh_library",
    "scene_3d_gridmap_get_cell": "cmd_gridmap_get_cell",
    "scene_3d_gridmap_set_cell": "cmd_gridmap_set_cell",
    "scene_3d_setup_camera": "cmd_setup_camera",
    "scene_3d_setup_environment": "cmd_setup_environment",
    "scene_3d_setup_lighting": "cmd_setup_lighting",
    "scene_edit_add_to_group": "cmd_add_to_group",
    "scene_edit_attach_script": "cmd_attach_script",
    "scene_edit_close_scene": "cmd_close_scene",
    "scene_edit_connect_signal": "cmd_connect_signal",
    "scene_edit_create_node": "cmd_create_node",
    "scene_edit_create_scene": "cmd_create_scene",
    "scene_edit_delete_node": "cmd_delete_node",
    "scene_edit_disconnect_signal": "cmd_disconnect_signal",
    "scene_edit_duplicate_node": "cmd_duplicate_node",
    "scene_edit_instance_scene": "cmd_instance_scene",
    "scene_edit_list_open_scenes": "cmd_list_open_scenes",
    "scene_edit_list_signal_connections": "cmd_list_signal_connections",
    "scene_edit_move_node": "cmd_move_node",
    "scene_edit_open_scene": "cmd_open_scene",
    "scene_edit_reload_scene": "cmd_reload_scene",
    "scene_edit_remove_from_group": "cmd_remove_from_group",
    "scene_edit_rename_node": "cmd_rename_node",
    "scene_edit_save_all_scenes": "cmd_save_all_scenes",
    "scene_edit_save_scene": "cmd_save_scene",
    "scene_edit_select_nodes": "cmd_select_nodes",
    "scene_edit_set_node_property": "cmd_set_node_property",
    "scripts_get_for_node": "cmd_get_script_for_node",
    "scripts_list": "cmd_list_scripts",
    "scripts_patch": "cmd_patch_script",
    "scripts_read": "cmd_read_script",
    "scripts_write": "cmd_write_script",
    "shader_assign_material": "cmd_assign_shader_material",
    "shader_create": "cmd_create_shader",
    "shader_get_param": "cmd_get_shader_param",
    "shader_read": "cmd_read_shader",
    "shader_set_param": "cmd_set_shader_param",
    "theme_ui_create": "cmd_create_theme",
    "theme_ui_get_node_overrides": "cmd_get_node_theme_overrides",
    "theme_ui_set_color": "cmd_set_theme_color",
    "theme_ui_set_font_size": "cmd_set_theme_font_size",
    "theme_ui_set_stylebox": "cmd_set_theme_stylebox",
    "tilemap_add_tileset_atlas_source": "cmd_add_tileset_atlas_source",
    "tilemap_clear": "cmd_tilemap_clear",
    "tilemap_create_tile": "cmd_create_tile",
    "tilemap_create_tileset": "cmd_create_tileset",
    "tilemap_fill_rect": "cmd_tilemap_fill_rect",
    "tilemap_get_cell": "cmd_tilemap_get_cell",
    "tilemap_get_used_cells": "cmd_tilemap_get_used_cells",
    "tilemap_layers": "cmd_tilemap_layers",
    "tilemap_set_cell": "cmd_tilemap_set_cell",
    "undo": "cmd_undo",
    "visual_shader_add_node": "cmd_add_shader_node",
    "visual_shader_connect_nodes": "cmd_connect_shader_nodes",
    "visual_shader_create": "cmd_create_visual_shader",
    "visual_shader_list_node_types": "cmd_list_shader_node_types",
    "visual_shader_read": "cmd_read_visual_shader",
    "visual_shader_set_node_param": "cmd_set_shader_node_param",
}

# Param keys the tool layer renames before sending to the addon, per bare
# handler name (the resolved cmd_* minus its ``cmd_`` prefix). The tool
# signatures use agent-friendly keys; the addon expects the canonical envelope
# keys (create/compose: ``node_name`` -> ``name``).
PARAM_ALIASES: dict[str, dict[str, str]] = {
    "create_node": {"node_name": "name"},
    "compose_node": {"node_name": "name"},
}

# Multi-step orchestrators: names an agent might try that can NOT be one batch
# entry. Reported with a targeted hint instead of a generic unknown-name error.
ORCHESTRATORS: dict[str, str] = {
    "run_test_scenario": (
        "plays a scene, injects inputs and evaluates assertions in one tool;"
        " call it directly instead"
    ),
    "testing_run_test_scenario": (
        "plays a scene, injects inputs and evaluates assertions in one tool;"
        " call it directly instead"
    ),
    "run_stress_test": "a play + repeated-input workflow; call it directly instead",
    "testing_run_stress_test": "a play + repeated-input workflow; call it directly instead",
    "run_tests": (
        "a headless GUT run via the Godot binary, not a bridge command;"
        " call it directly instead"
    ),
    "testing_run_tests": (
        "a headless GUT run via the Godot binary, not a bridge command;"
        " call it directly instead"
    ),
    "export_project": (
        "a headless export via the Godot binary, not a bridge command;"
        " call it directly instead"
    ),
    "debug_workflow": "an aggregator over several read-only checks; call it directly instead",
    "assert_node_state": "polls the runtime probe (monitor + samples); call it directly instead",
    "testing_assert_node_state": (
        "polls the runtime probe (monitor + samples); call it directly instead"
    ),
    "run_and_capture": (
        "runs the project headless via the Godot binary, not a bridge command;"
        " call it directly instead"
    ),
    "runtime_run_and_capture": (
        "runs the project headless via the Godot binary, not a bridge command;"
        " call it directly instead"
    ),
}


def _suggest(miss: str) -> str | None:
    """Closest known bare name for a failed lookup, or None.

    Similarity = longest common substring (not just prefix), so
    ``set_layerz`` finds ``physics_set_layers``. Ties break toward the
    shorter name (closer to the plain handler form).
    """
    best: tuple[int, str] | None = None
    for known in BARE_TO_COMMAND:
        # Longest common substring between the miss and the known name.
        common = 0
        for i in range(len(miss)):
            for j in range(len(known)):
                k = 0
                while i + k < len(miss) and j + k < len(known) and miss[i + k] == known[j + k]:
                    k += 1
                if k > common:
                    common = k
        if common == 0:
            continue
        if best is None or common > best[0] or (common == best[0] and len(known) < len(best[1])):
            best = (common, known)
    return best[1] if best else None


def resolve_command(command: str) -> str:
    """Resolve a sub-command to the addon ``cmd_*`` form.

    Accepts (in order): the ``cmd_*`` form verbatim; a bare name from the
    registry table (trimmed/reordered exposed names, with or without the
    toolset prefix); a plain handler name (``create_node`` →
    ``cmd_create_node``). Raises ``ToolError`` with a targeted hint on a miss.
    """
    from fastmcp.exceptions import ToolError

    if command.startswith("cmd_"):
        return command
    if command in BARE_TO_COMMAND:
        return BARE_TO_COMMAND[command]
    # Registry-table names carry their toolset prefix; accept the same name
    # with a known prefix stripped ("create_node" == the bare of
    # "scene_edit_create_node"). Exactly one match resolves; more than one
    # (e.g. "set_layers" matching both physics and navigation) is ambiguous —
    # fail naming the matches rather than silently picking one.
    hits = [known for known in BARE_TO_COMMAND if known.endswith(f"_{command}")]
    if len(hits) == 1:
        return BARE_TO_COMMAND[hits[0]]
    if len(hits) > 1:
        # Multiple toolsets expose the same action. Disambiguate the way the
        # addon does: the bare form is genuinely ambiguous, so ask the caller
        # to use the prefixed form rather than silently picking one.
        raise ToolError(
            f"VALIDATION_ERROR: '{command}' is ambiguous — matches {', '.join(sorted(hits))}. "
            f"Use the prefixed bare form (e.g. '{sorted(hits)[0]}') or the cmd_* form."
        )
    # Last resort: treat the input as a plain handler name.
    if f"cmd_{command}" in set(BARE_TO_COMMAND.values()):
        return f"cmd_{command}"
    # Known orchestrator? Point at the real tool instead of "unknown".
    if command in ORCHESTRATORS:
        raise ToolError(
            f"VALIDATION_ERROR: '{command}' is a multi-step orchestrator, not a single "
            f"bridge command — it {ORCHESTRATORS[command]}."
        )
    suggestion = _suggest(command)
    hint = f"Unknown command '{command}'."
    if suggestion:
        hint += f" Did you mean '{suggestion}'?"
    else:
        hint += (
            " Use the exposed tool name without the 'godot_' prefix"
            " (e.g. 'scene_edit_create_node') or the addon cmd_* form."
        )
    raise ToolError(f"VALIDATION_ERROR: {hint}")


def map_params(bare_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Translate a batch entry's params to the addon's envelope keys.

    Applies the per-name alias table (``node_name`` -> ``name``); unknown keys
    pass through untouched so the addon's own validation reports them.
    """
    aliases = PARAM_ALIASES.get(bare_name)
    if not aliases:
        return params
    mapped = dict(params)
    for source, target in aliases.items():
        if target in mapped:
            # Explicit target wins; drop the alias so the addon sees one key.
            mapped.pop(source, None)
        elif source in mapped:
            mapped[target] = mapped.pop(source)
    return mapped


__all__ = ["BARE_TO_COMMAND", "ORCHESTRATORS", "PARAM_ALIASES", "map_params", "resolve_command"]