"""Contract tests: every Tier 1/2 scene mutation carries the addon's persistence verdict (#458).

The addon decides ``persisted``/``reason``/``hint``; the server's job is to pass them
through untouched — including tools that build their result by hand — and to leave them
unknown on a ``dry_run`` preview, where no editor was asked.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# node path -> the verdict the fake addon stamps for it
VERDICTS: dict[str, dict[str, Any]] = {
    "Own": {"persisted": True},
    "Relic/Orb": {
        "persisted": False,
        "reason": "instanced_child_not_editable",
        "hint": "Enable Editable Children on 'Relic', or target a node the scene owns.",
    },
    "Relic2/Orb": {
        "persisted": False,
        "reason": "embedded_in_other_resource",
        "hint": "Edit it in 'res://relic.tscn' directly.",
    },
    "Base/Label": {
        "persisted": False,
        "reason": "group_from_base_scene",
        "hint": "Remove it in 'res://base.tscn' instead.",
    },
}

# (exposed tool, toolset category, addon command, args without the target node)
TOOLS: list[tuple[str, str, str, dict[str, Any]]] = [
    ("godot_scene_edit_rename_node", "scene_edit", "cmd_rename_node", {"new_name": "Moved"}),
    (
        "godot_scene_edit_set_node_property",
        "scene_edit",
        "cmd_set_node_property",
        {"property": "visible", "value": False},
    ),
    (
        "godot_scene_edit_attach_script",
        "scene_edit",
        "cmd_attach_script",
        {"script_path": "res://a.gd"},
    ),
    ("godot_scene_edit_add_to_group", "scene_edit", "cmd_add_to_group", {"group": "g"}),
    ("godot_scene_edit_remove_from_group", "scene_edit", "cmd_remove_from_group", {"group": "g"}),
    ("godot_theme_ui_create", "theme_ui", "cmd_create_theme", {}),
    (
        "godot_theme_ui_set_color",
        "theme_ui",
        "cmd_set_theme_color",
        {"name": "font_color", "color": "#ffffff"},
    ),
    (
        "godot_theme_ui_set_font_size",
        "theme_ui",
        "cmd_set_theme_font_size",
        {"name": "font_size", "size": 12},
    ),
    ("godot_theme_ui_set_stylebox", "theme_ui", "cmd_set_theme_stylebox", {"name": "normal"}),
    ("godot_physics_setup_body", "physics", "cmd_setup_physics_body", {"properties": {}}),
    ("godot_physics_set_layers", "physics", "cmd_set_physics_layers", {"layers": [1]}),
    ("godot_navigation_set_layers", "navigation", "cmd_set_navigation_layers", {"layers": [1]}),
    ("godot_navigation_bake_mesh", "navigation", "cmd_bake_navigation_mesh", {}),
    (
        "godot_particles_set_material",
        "particles",
        "cmd_set_particle_material",
        {"properties": {"spread": 1.0}},
    ),
    (
        "godot_particles_set_color_gradient",
        "particles",
        "cmd_set_particle_color_gradient",
        {"colors": ["#ffffff", "#000000"]},
    ),
    ("godot_particles_apply_preset", "particles", "cmd_apply_particle_preset", {"preset": "fire"}),
    ("godot_scene_3d_create_mesh_library", "scene_3d", "cmd_create_mesh_library", {}),
    (
        "godot_scene_3d_add_mesh_library_item",
        "scene_3d",
        "cmd_add_mesh_library_item",
        {"mesh_type": "BoxMesh"},
    ),
    (
        "godot_scene_3d_gridmap_set_cell",
        "scene_3d",
        "cmd_gridmap_set_cell",
        {"position": [0, 0, 0], "item": 0},
    ),
    ("godot_tilemap_create_tileset", "tilemap", "cmd_create_tileset", {}),
    (
        "godot_tilemap_add_tileset_atlas_source",
        "tilemap",
        "cmd_add_tileset_atlas_source",
        {"texture_path": "res://t.png", "region_size": [16, 16]},
    ),
    (
        "godot_tilemap_create_tile",
        "tilemap",
        "cmd_create_tile",
        {"source_id": 0, "atlas_coords": [0, 0]},
    ),
    (
        "godot_tilemap_set_cell",
        "tilemap",
        "cmd_tilemap_set_cell",
        {"coords": [0, 0], "source_id": 0},
    ),
    (
        "godot_tilemap_fill_rect",
        "tilemap",
        "cmd_tilemap_fill_rect",
        {"rect": [0, 0, 1, 1], "source_id": 0},
    ),
    ("godot_tilemap_clear", "tilemap", "cmd_tilemap_clear", {}),
    ("godot_animation_create", "animation", "cmd_create_animation", {"name": "run"}),
    (
        "godot_animation_add_track",
        "animation",
        "cmd_add_animation_track",
        {"animation": "idle", "track_path": "Sprite:modulate"},
    ),
    (
        "godot_animation_insert_keyframe",
        "animation",
        "cmd_insert_keyframe",
        {"animation": "idle", "track": 0, "time": 0.0, "value": 1.0},
    ),
    (
        "godot_animation_add_state_machine_state",
        "animation",
        "cmd_add_state_machine_state",
        {"state_name": "Jump"},
    ),
    (
        "godot_animation_set_blend_tree_node",
        "animation",
        "cmd_set_blend_tree_node",
        {"node_name": "Mix", "node_type": "AnimationNodeAdd2"},
    ),
]
TREE_TOOLS = {"cmd_add_state_machine_state", "cmd_set_blend_tree_node"}  # take tree_path


def _target(command: str, node_path: str) -> dict[str, str]:
    return {"tree_path" if command in TREE_TOOLS else "node_path": node_path}


def _fake_value(schema: dict[str, Any]) -> Any:
    """A value of the schema's type — enough for the result model to validate."""
    options = schema.get("anyOf", [schema])
    kind = next((o.get("type") for o in options if o.get("type") not in (None, "null")), None)
    return {"string": "x", "integer": 0, "number": 0.0, "boolean": True, "array": []}.get(
        str(kind), {}
    )


class _Addon:
    """A fake addon: answers each mutation with its tool's required result fields plus the
    verdict for the target node."""

    def __init__(self) -> None:
        self.schemas: dict[str, dict[str, Any]] = {}

    def __call__(self, cmd: CommandEnvelope) -> ResponseEnvelope | None:
        p = cmd.params
        if cmd.command == "cmd_node_exists":  # require_node_exists precondition
            return ResponseEnvelope.success(cmd.id, {"exists": True})
        schema = self.schemas.get(cmd.command)
        if schema is None:
            return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", f"unexpected {cmd.command}")
        props = schema.get("properties", {})
        result = {name: _fake_value(props[name]) for name in schema.get("required", [])}
        # the two group tools read the addon's own flag rather than a result field
        result.update({"added": True, "removed": True})
        target = p.get("tree_path", p.get("node_path", ""))
        return ResponseEnvelope.success(cmd.id, {**result, **VERDICTS[target]})


async def _build(addon: _Addon, client: Client) -> None:
    for category in sorted({category for _, category, _, _ in TOOLS}):
        await client.call_tool("godot_enable_toolset", {"category": category})
    listed = {t.name: t for t in await client.list_tools()}
    for tool, _, command, _ in TOOLS:
        assert tool in listed, f"{tool} is not registered"
        addon.schemas[command] = listed[tool].output_schema or {}


def _server() -> tuple[FastMCP, _Addon, FakeAddonConnection]:
    addon = _Addon()
    conn = FakeAddonConnection(responder=addon)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), addon, conn


@pytest.mark.parametrize("node_path", ["Own", "Relic/Orb", "Relic2/Orb"])
async def test_every_mutation_passes_the_verdict_through(node_path: str) -> None:
    server, addon, _ = _server()
    async with Client(server) as client:
        await _build(addon, client)
        for tool, _, command, args in TOOLS:
            result = await client.call_tool(tool, {**_target(command, node_path), **args})
            content = result.structured_content
            assert content is not None, tool
            for key in ("persisted", "reason", "hint"):
                assert content.get(key) == VERDICTS[node_path].get(key), (tool, key, content)


async def test_group_removal_from_base_scene_is_reported() -> None:
    server, addon, _ = _server()
    async with Client(server) as client:
        await _build(addon, client)
        result = await client.call_tool(
            "godot_scene_edit_remove_from_group", {"node_path": "Base/Label", "group": "g"}
        )
    content = result.structured_content
    assert content["changed"] is True and content["in_group"] is False
    assert content["persisted"] is False
    assert content["reason"] == "group_from_base_scene"
    assert "base.tscn" in content["hint"]


async def test_dry_run_leaves_persistence_unknown() -> None:
    """Only the editor can judge persistence; a preview must not claim either way."""
    server, addon, conn = _server()
    async with Client(server) as client:
        await _build(addon, client)
        for tool, _, command, args in TOOLS:
            result = await client.call_tool(
                tool, {**_target(command, "Relic/Orb"), **args, "dry_run": True}
            )
            content = result.structured_content
            assert content is not None, tool
            assert content.get("persisted") is None, (tool, content)
            assert content.get("reason") is None and content.get("hint") is None, tool
    sent = {CommandEnvelope.model_validate_json(s).command for s in conn.sent}
    assert not sent & {command for _, _, command, _ in TOOLS}
