"""Smoke checks for the Godot addon scaffold (issue #1).

The addon side cannot be unit-tested by running Godot here, so these pin the
parts that are statically checkable: the ``plugin.cfg`` manifest is well-formed
and points at a real ``@tool extends EditorPlugin`` script, the project enables
the plugin, and the addon version stays in lockstep with the Python package
(both CalVer). Loading the plugin in the Godot 4.4 editor is the addon-side
preflight (see .claude/rules/workflow.md).
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

import mcp_server

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
PLUGIN_CFG = ADDON_DIR / "plugin.cfg"
PROJECT_GODOT = REPO_ROOT / "godot" / "project.godot"
CALVER = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:-\d+)?$")


@pytest.fixture
def plugin_cfg() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(PLUGIN_CFG)
    return parser


def test_plugin_cfg_exists() -> None:
    assert PLUGIN_CFG.is_file(), f"missing addon manifest at {PLUGIN_CFG}"


@pytest.mark.parametrize("key", ["name", "description", "author", "version", "script"])
def test_plugin_cfg_has_required_keys(plugin_cfg: configparser.ConfigParser, key: str) -> None:
    assert plugin_cfg.has_option("plugin", key), f"plugin.cfg [plugin] missing {key!r}"
    assert plugin_cfg.get("plugin", key).strip('"'), f"plugin.cfg {key!r} is empty"


def test_plugin_script_exists_and_is_editor_plugin(
    plugin_cfg: configparser.ConfigParser,
) -> None:
    script_name = plugin_cfg.get("plugin", "script").strip('"')
    script_path = ADDON_DIR / script_name
    assert script_path.is_file(), f"plugin script {script_name!r} not found"
    source = script_path.read_text()
    assert "@tool" in source, "addon script must carry @tool"
    assert "extends EditorPlugin" in source, "addon entry must extend EditorPlugin"


def test_addon_version_matches_package(plugin_cfg: configparser.ConfigParser) -> None:
    version = plugin_cfg.get("plugin", "version").strip('"')
    assert CALVER.match(version), f"addon version {version!r} is not CalVer"
    assert version == mcp_server.__version__, "addon and server versions drifted"


def test_project_godot_enables_plugin() -> None:
    assert PROJECT_GODOT.is_file(), "godot/project.godot must exist so the addon is loadable"
    text = PROJECT_GODOT.read_text()
    assert "res://addons/godot_mcp/plugin.cfg" in text, "project must enable the godot_mcp plugin"


def test_dock_script_exists_and_is_tool() -> None:
    dock = ADDON_DIR / "mcp_dock.gd"
    assert dock.is_file(), "status dock script mcp_dock.gd must exist"
    source = dock.read_text()
    assert "@tool" in source, "dock script must carry @tool"
    assert "class_name MCPStatusDock" in source, "dock must expose a class_name for typed use"
    # The dock is read-only this phase: no editor mutation API leaks into it.
    assert "EditorInterface" not in source, "dock must stay editor-independent (plugin feeds it)"


def test_plugin_wires_the_dock() -> None:
    source = (ADDON_DIR / "godot_mcp.gd").read_text()
    assert "MCPStatusDock" in source, "plugin must instantiate the typed dock"
    assert "add_control_to_dock" in source, "plugin must add the dock to an editor dock slot"
    assert "remove_control_from_docks" in source, "plugin must remove the dock on _exit_tree"


def test_command_router_exists() -> None:
    router = ADDON_DIR / "command_router.gd"
    assert router.is_file(), "command_router.gd must exist"
    source = router.read_text()
    assert "@tool" in source
    assert "class_name MCPCommandRouter" in source


def test_bridge_uses_websocket_transport() -> None:
    bridge = ADDON_DIR / "mcp_bridge.gd"
    assert bridge.is_file(), "mcp_bridge.gd must exist"
    source = bridge.read_text()
    assert "@tool" in source
    assert "class_name MCPBridge" in source
    # The bridge is a WebSocket *client* now (#276): it connects out to the server's
    # listener and reconnects, rather than running a TCPServer.
    assert "WebSocketPeer" in source, "bridge must use WebSocketPeer"
    assert "connect_to_url" in source, "bridge must connect out as a client"
    assert "TCPServer" not in source, "bridge no longer listens (direction inverted, #276)"


def test_plugin_wires_the_bridge() -> None:
    source = (ADDON_DIR / "godot_mcp.gd").read_text()
    assert "MCPBridge" in source, "plugin must start the bridge"
    assert "_bridge.stop()" in source, "plugin must stop the bridge on _exit_tree"


def test_inspection_helpers_exist() -> None:
    coerce = ADDON_DIR / "type_coerce.gd"
    inspect = ADDON_DIR / "scene_inspect.gd"
    assert coerce.is_file() and "class_name MCPTypeCoerce" in coerce.read_text()
    assert inspect.is_file() and "class_name MCPSceneInspect" in inspect.read_text()


def test_router_registers_inspection_commands() -> None:
    sources = [ADDON_DIR / "command_router.gd", ADDON_DIR / "handlers" / "scene_inspect.gd"]
    for src in sources:
        assert src.exists(), f"required source missing: {src}"
    combined = "".join(src.read_text() for src in sources)
    # Wire commands are cmd_-prefixed (the handler name); see docs/architecture.md.
    for command in (
        "cmd_get_project_info",
        "cmd_get_active_scene",
        "cmd_get_scene_tree",
        "cmd_get_selected_node",
        "cmd_get_node_properties",
    ):
        assert f'"{command}"' in combined, f"router must register {command}"


def test_router_registers_mutation_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_create_node",
        "cmd_rename_node",
        "cmd_set_node_property",
        "cmd_delete_node",
        "cmd_attach_script",
        "cmd_connect_signal",
        "cmd_save_scene",
        "cmd_create_scene",
        "cmd_instance_scene",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_script_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_read_script",
        "cmd_list_scripts",
        "cmd_get_script_for_node",
        "cmd_write_script",
        "cmd_patch_script",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_node_parity_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_duplicate_node",
        "cmd_move_node",
        "cmd_add_to_group",
        "cmd_remove_from_group",
        "cmd_list_signal_connections",
        "cmd_disconnect_signal",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_composite_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in ("cmd_compose_node", "cmd_batch_create_nodes", "cmd_apply_node_edits"):
        assert f'"{command}"' in source, f"router must register {command}"
    # Each of the three composites must wrap its tree mutation in exactly one
    # UndoRedo action: one create_action + one commit_action per handler.
    composite = (ADDON_DIR / "handlers" / "composite.gd").read_text()
    assert composite.count(".create_action(") == 3
    assert composite.count(".commit_action(") == 3


def test_router_registers_resource_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_read_resource",
        "cmd_create_resource",
        "cmd_set_resource_property",
        "cmd_register_autoload",
        "cmd_unregister_autoload",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_project_fs_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_get_filesystem_tree",
        "cmd_search_files",
        "cmd_get_setting",
        "cmd_set_setting",
        "cmd_path_to_uid",
        "cmd_uid_to_path",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_editor_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    assert '"cmd_capture_editor_screenshot"' in source
    # Capture uses the verified Image → base64 PNG chain.
    assert "save_png_to_buffer" in source and "raw_to_base64" in source


def test_router_registers_physics_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_setup_physics_body",
        "cmd_setup_collision",
        "cmd_set_physics_layers",
        "cmd_add_raycast",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_animation_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_create_animation",
        "cmd_add_animation_track",
        "cmd_insert_keyframe",
        "cmd_create_animation_tree",
        "cmd_add_state_machine_state",
        "cmd_set_blend_tree_node",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_scene_3d_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_add_mesh_instance",
        "cmd_setup_camera",
        "cmd_setup_lighting",
        "cmd_setup_environment",
        "cmd_gridmap_set_cell",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_particle_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_create_particles",
        "cmd_set_particle_material",
        "cmd_set_particle_color_gradient",
        "cmd_apply_particle_preset",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_navigation_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_setup_navigation_region",
        "cmd_setup_navigation_agent",
        "cmd_bake_navigation_mesh",
        "cmd_set_navigation_layers",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_audio_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_add_audio_player",
        "cmd_get_audio_bus_layout",
        "cmd_add_audio_bus",
        "cmd_add_audio_bus_effect",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_tilemap_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_tilemap_set_cell",
        "cmd_tilemap_fill_rect",
        "cmd_tilemap_get_cell",
        "cmd_tilemap_clear",
        "cmd_tilemap_layers",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_theme_ui_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_create_theme",
        "cmd_set_theme_color",
        "cmd_set_theme_font_size",
        "cmd_set_theme_stylebox",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_shader_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_create_shader",
        "cmd_read_shader",
        "cmd_assign_shader_material",
        "cmd_set_shader_param",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_runtime_session_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_play_scene",
        "cmd_stop_scene",
        "cmd_is_playing",
        "cmd_get_game_scene_tree",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_runtime_session_addon_files_present() -> None:
    # The EditorDebuggerPlugin captures the played game's godot_mcp channel; the probe
    # autoload (game-side) answers its queries. Both must ship in the addon (issue #66).
    debugger = ADDON_DIR / "mcp_debugger.gd"
    probe = ADDON_DIR / "mcp_runtime_probe.gd"
    assert debugger.exists() and "EditorDebuggerPlugin" in debugger.read_text()
    assert probe.exists() and "register_message_capture" in probe.read_text()
    # The plugin entry must register/unregister the debugger plugin and wire it to the router.
    entry = (ADDON_DIR / "godot_mcp.gd").read_text()
    assert "add_debugger_plugin" in entry and "remove_debugger_plugin" in entry
    assert "set_debugger" in entry


def test_router_registers_scene_session_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_open_scene",
        "cmd_reload_scene",
        "cmd_save_all_scenes",
        "cmd_list_open_scenes",
        "cmd_select_nodes",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_input_map_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_add_input_action",
        "cmd_remove_input_action",
        "cmd_add_input_event",
        "cmd_clear_input_action_events",
    ):
        assert f'"{command}"' in source, f"router must register {command}"


def test_router_registers_input_sim_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_simulate_key",
        "cmd_simulate_mouse",
        "cmd_simulate_action",
        "cmd_play_input_sequence",
        "cmd_get_input_stats",
    ):
        assert f'"{command}"' in source, f"router must register {command}"
    # The runtime probe must inject via Input.parse_input_event / action_press.
    probe = (ADDON_DIR / "mcp_runtime_probe.gd").read_text()
    assert "parse_input_event" in probe and "action_press" in probe


def test_router_registers_runtime_inspect_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in ("cmd_monitor_property", "cmd_get_property_samples", "cmd_find_ui_elements"):
        assert f'"{command}"' in source, f"router must register {command}"
    # The probe must sample properties and collect Control nodes with their rect.
    probe = (ADDON_DIR / "mcp_runtime_probe.gd").read_text()
    assert "_start_monitor" in probe and "get_global_rect" in probe


def test_router_registers_input_recording_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in ("cmd_record_input", "cmd_stop_recording", "cmd_get_recording"):
        assert f'"{command}"' in source, f"router must register {command}"
    # The probe must capture input via _input and serialize events for replay.
    probe = (ADDON_DIR / "mcp_runtime_probe.gd").read_text()
    assert "func _input(" in probe and "_serialize_event" in probe


def test_router_registers_profiling_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in ("cmd_get_editor_performance", "cmd_get_performance_monitors"):
        assert f'"{command}"' in source, f"router must register {command}"
    assert "Performance.get_monitor" in source  # editor snapshot reads the monitors
    probe = (ADDON_DIR / "mcp_runtime_probe.gd").read_text()
    assert "_performance_snapshot" in probe  # the probe answers get_performance


def test_router_registers_batch_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in (
        "cmd_find_nodes_by_type",
        "cmd_batch_set_property",
        "cmd_cross_scene_set_property",
        "cmd_get_dependencies",
    ):
        assert f'"{command}"' in source, f"router must register {command}"
    # cross-scene edits load with GEN_EDIT_STATE_MAIN and re-pack/save faithfully.
    assert "GEN_EDIT_STATE_MAIN" in source and "ResourceLoader.get_dependencies" in source


def test_router_registers_export_commands() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    for command in ("cmd_list_export_presets", "cmd_get_export_info"):
        assert f'"{command}"' in source, f"router must register {command}"
    # presets are read from export_presets.cfg via Godot's ConfigFile.
    assert "export_presets.cfg" in source and "ConfigFile" in source


def test_plugin_declares_minimum_godot_version() -> None:
    # The addon supports Godot 4.4+ and warns (not crashes) on older editors (issue #86).
    entry = (ADDON_DIR / "godot_mcp.gd").read_text()
    assert "MIN_GODOT_MAJOR := 4" in entry and "MIN_GODOT_MINOR := 4" in entry
    assert "_warn_if_unsupported_version" in entry
    assert "Engine.get_version_info()" in entry
    # The example project itself targets 4.7 (validated on 4.7-stable, #200); the
    # addon's support floor above stays 4.4+. The feature string flags older editor opens.
    assert '"4.7"' in PROJECT_GODOT.read_text()


def test_mutations_use_undo_redo() -> None:
    source = "".join(f.read_text() for f in ADDON_DIR.rglob("*.gd"))
    # Every create/rename/delete/set must register with EditorUndoRedoManager.
    assert "get_editor_undo_redo" in source
    assert source.count("create_action") >= 6  # the UndoRedo-wrapped mutations
