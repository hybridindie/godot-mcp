"""Contract tests for server-side ``res://`` path containment (issue #637).

Containment must not depend on the addon's ``begins_with("res://")`` check
(which accepts ``res://../x`` and ``res:///etc``). Every file-path tool
parameter is annotated with :data:`mcp_server.paths.ResPath` (or ``ExportPath``
for export output), so a bad path is rejected at the schema boundary. A drift
test enumerates all ``*path*``/``directory`` parameters so a new tool cannot
ship without containment. Node paths (``Player/Gun``) are the documented
exception.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_TOOLS_DIR = pathlib.Path("mcp_server/tools")
_CONTAINMENT_TYPES = {"ResPath", "ExportPath"}

# Every node-path parameter: a Godot node path (``Player/Gun``), NOT a ``res://``
# file path, so containment does not apply. Everything else whose name contains
# "path" (or is "directory") must use a containment type.
NODE_PATH_PARAMS: frozenset[tuple[str, str]] = frozenset(
    {
        ("create_animation", "node_path"),
        ("add_animation_track", "node_path"),
        ("add_animation_track", "track_path"),
        ("insert_keyframe", "node_path"),
        ("create_animation_tree", "parent_path"),
        ("add_state_machine_state", "tree_path"),
        ("set_blend_tree_node", "tree_path"),
        ("list_animations", "node_path"),
        ("get_animation", "node_path"),
        ("add_audio_player", "parent_path"),
        ("find_nodes_by_type", "parent_path"),
        ("batch_set_property", "node_paths"),
        ("compose_node", "parent_path"),
        ("batch_create_nodes", "parent_path"),
        ("create_node", "parent_path"),
        ("rename_node", "node_path"),
        ("set_node_property", "node_path"),
        ("delete_node", "node_path"),
        ("attach_script", "node_path"),
        ("connect_signal", "source_path"),
        ("connect_signal", "target_path"),
        ("disconnect_signal", "source_path"),
        ("disconnect_signal", "target_path"),
        ("create_scene", "root_type"),
        ("instance_scene", "parent_path"),
        ("extract_scene", "node_path"),
        ("set_editable_children", "node_path"),
        ("duplicate_node", "node_path"),
        ("move_node", "node_path"),
        ("move_node", "new_parent_path"),
        ("add_to_group", "node_path"),
        ("remove_from_group", "node_path"),
        ("list_signal_connections", "node_path"),
        ("setup_navigation_region", "parent_path"),
        ("setup_navigation_agent", "parent_path"),
        ("bake_navigation_mesh", "node_path"),
        ("set_navigation_layers", "node_path"),
        ("get_navigation_region", "node_path"),
        ("create_particles", "parent_path"),
        ("set_particle_material", "node_path"),
        ("set_particle_color_gradient", "node_path"),
        ("apply_particle_preset", "node_path"),
        ("get_particle_material", "node_path"),
        ("setup_physics_body", "node_path"),
        ("setup_collision", "node_path"),
        ("set_physics_layers", "node_path"),
        ("add_raycast", "parent_path"),
        ("monitor_property", "node_path"),
        ("read_property", "node_path"),
        ("add_mesh_instance", "parent_path"),
        ("setup_camera", "parent_path"),
        ("setup_lighting", "parent_path"),
        ("setup_environment", "parent_path"),
        ("gridmap_set_cell", "node_path"),
        ("gridmap_get_cell", "node_path"),
        ("create_mesh_library", "node_path"),
        ("add_mesh_library_item", "node_path"),
        ("select_nodes", "node_paths"),
        ("assign_shader_material", "node_path"),
        ("set_shader_param", "node_path"),
        ("get_shader_param", "node_path"),
        ("assert_node_state", "node_path"),
        ("tilemap_set_cell", "node_path"),
        ("tilemap_fill_rect", "node_path"),
        ("tilemap_get_cell", "node_path"),
        ("tilemap_get_used_cells", "node_path"),
        ("tilemap_clear", "node_path"),
        ("tilemap_layers", "node_path"),
        ("create_tileset", "node_path"),
        ("add_tileset_atlas_source", "node_path"),
        ("create_tile", "node_path"),
        ("create_theme", "node_path"),
        ("set_theme_color", "node_path"),
        ("set_theme_font_size", "node_path"),
        ("set_theme_stylebox", "node_path"),
        ("get_node_theme_overrides", "node_path"),
        ("get_node_properties", "node_path"),
        ("get_node_property", "node_path"),
        ("get_node_property_list", "node_path"),
        ("get_node_groups", "node_path"),
        ("snapshot_subtree", "node_path"),
        ("diff_snapshots", "node_path"),
        ("get_script_for_node", "node_path"),
    }
)


def _is_path_param(name: str) -> bool:
    return name == "directory" or "path" in name


def _tool_path_params() -> list[tuple[str, str, str]]:
    """(function name, param name, annotation source) for every tool path param."""
    out: list[tuple[str, str, str]] = []
    for path in sorted(_TOOLS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "tool"
                for d in node.decorator_list
            ):
                continue
            for arg in node.args.args:
                if _is_path_param(arg.arg):
                    annotation = ast.unparse(arg.annotation) if arg.annotation else "?"
                    out.append((node.name, arg.arg, annotation))
    return out


def test_every_file_path_param_uses_a_containment_type() -> None:
    def _contained(annotation: str) -> bool:
        base = annotation.split("|")[0].strip()
        return base in _CONTAINMENT_TYPES or base in {
            f"list[{t}]" for t in _CONTAINMENT_TYPES
        }

    offenders = [
        f"{func}.{param} ({annotation})"
        for func, param, annotation in _tool_path_params()
        if not _contained(annotation) and (func, param) not in NODE_PATH_PARAMS
    ]
    assert not offenders, (
        "file-path tool params must use ResPath/ExportPath (issue #637) or be "
        "listed in NODE_PATH_PARAMS: " + ", ".join(offenders)
    )


def test_node_path_exemptions_are_real_node_paths() -> None:
    """Guard the exemption list: it must not hide a real file-path param."""
    annotated = {
        (func, param): annotation
        for func, param, annotation in _tool_path_params()
        if annotation.split("|")[0].strip() in _CONTAINMENT_TYPES
    }
    overlap = set(annotated) & NODE_PATH_PARAMS
    assert not overlap, f"params both annotated and node-exempt: {sorted(overlap)}"


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


@pytest.mark.parametrize("bad", ["res://../evil.tres", "/etc/evil.tres", "evil.tres"])
async def test_create_resource_rejects_uncontained_path(bad: str) -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "godot_resources_edit_create_resource",
            {"type": "Resource", "resource_path": bad},
            raise_on_error=False,
        )
    assert result.is_error
    assert "cmd_create_resource" not in _commands(conn)


@pytest.mark.parametrize("bad", ["res://../evil.gdshader", "/etc/evil.gdshader"])
async def test_create_shader_rejects_uncontained_path(bad: str) -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "shader"})
        result = await client.call_tool(
            "godot_shader_create",
            {"shader_path": bad, "code": "shader_type canvas_item;"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "cmd_create_shader" not in _commands(conn)


class _FakeExportRunner:
    """Minimal Runner: records export targets, never launches Godot."""

    binary: str | None = "fake-godot"

    def __init__(self) -> None:
        self.exports: list[str] = []

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"], exit_code=0)

    async def check_shader(self, project_dir: str, shader_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        self.exports.append(output_path)
        return RunOutput(command=["fake"], exit_code=0)

    async def run_tests(
        self, project_dir: str, test_dir: str, timeout: float, test_file: str = ""
    ) -> RunOutput:
        return RunOutput(command=["fake"], exit_code=0)


def _export_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_list_export_presets":
        return ResponseEnvelope.success(
            cmd.id,
            {
                "has_config": True,
                "presets": [
                    {
                        "index": 0,
                        "name": "Linux",
                        "platform": "Linux",
                        "runnable": True,
                        "export_path": "",
                    }
                ],
            },
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _export_server() -> tuple[FastMCP, _FakeExportRunner]:
    conn = FakeAddonConnection(responder=_export_responder)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    runner = _FakeExportRunner()
    return create_server(config, bridge=bridge, runner=runner), runner


async def test_export_output_outside_project_needs_confirm() -> None:
    server, runner = _export_server()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "export"})
        refused = await client.call_tool(
            "godot_export_project",
            {"preset": "Linux", "output_path": "/etc/evil.x86_64"},
            raise_on_error=False,
        )
        assert refused.is_error
        assert runner.exports == []  # never launched
        # Inside the project dir: allowed without confirm.
        await client.call_tool(
            "godot_export_project",
            {"preset": "Linux", "output_path": "build/game.x86_64"},
        )
        assert runner.exports == ["build/game.x86_64"]
        # Outside again, but explicitly confirmed: allowed.
        await client.call_tool(
            "godot_export_project",
            {"preset": "Linux", "output_path": "/tmp/out/game.x86_64", "confirm": True},
        )
        assert runner.exports[-1] == "/tmp/out/game.x86_64"


async def test_run_commands_subcommand_path_is_contained() -> None:
    """A ``run_commands`` entry bypasses the tool argument schema, so containment
    is re-checked in ``_route`` preflight (issue #637)."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "composite"})
        await client.call_tool("godot_enable_toolset", {"category": "resources_edit"})
        result = await client.call_tool(
            "godot_composite_run_commands",
            {
                "commands": [
                    {
                        "command": "cmd_create_resource",
                        "params": {"type": "Resource", "resource_path": "res://../evil.tres"},
                    }
                ]
            },
            raise_on_error=False,
        )
    assert result.is_error
    assert "cmd_run_commands" not in _commands(conn)
