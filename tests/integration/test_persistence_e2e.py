"""Persistence truth for scene mutations against a live editor (issue #458).

Every mutation below reports ``persisted``. Each verdict is checked against what actually
survives: the scenes are saved, then instantiated from disk in a separate headless Godot
process and read back. The fixtures cover a scene-owned node, an instance without Editable
Children ("Relic"), one with ("Relic2"), an inherited scene, resources embedded in the
instanced/base scene, and resources in their own ``.tres`` files.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, serve_and_await_editor

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://127.0.0.1:9097"
PREFIX = "tmp_e2e_persist2_"
MAIN = f"res://{PREFIX}main.tscn"
DERIVED = f"res://{PREFIX}derived.tscn"
TEX = f"res://{PREFIX}tex.tres"
SCRIPT = f"res://{PREFIX}script.gd"

NOT_EDITABLE = "instanced_child_not_editable"
EMBEDDED = "embedded_in_other_resource"
BASE_GROUP = "group_from_base_scene"
SETUP = "setup"  # a helper step: must succeed, carries no verdict

FIXTURES = {
    f"{PREFIX}tex.tres": """[gd_resource type="PlaceholderTexture2D" format=3]

[resource]
size = Vector2(64, 64)
""",
    f"{PREFIX}script.gd": "@tool\nextends Label\n",
    f"{PREFIX}inner.tscn": f"""[gd_scene format=3]

[ext_resource type="Texture2D" path="{TEX}" id="1"]

[sub_resource type="TileSetAtlasSource" id="src"]
texture = ExtResource("1")
0:0/0 = 0

[sub_resource type="TileSet" id="ts"]
sources/0 = SubResource("src")

[sub_resource type="BoxMesh" id="box"]

[sub_resource type="MeshLibrary" id="lib"]
item/0/name = "a"
item/0/mesh = SubResource("box")

[sub_resource type="Animation" id="idle"]
length = 1.0

[sub_resource type="AnimationLibrary" id="alib"]
_data = {{
&"idle": SubResource("idle")
}}

[sub_resource type="AnimationNodeStateMachine" id="sm"]

[sub_resource type="AnimationNodeBlendTree" id="bt"]

[sub_resource type="ParticleProcessMaterial" id="ppm"]
spread = 10.0

[node name="Inner" type="Node2D"]

[node name="Label" type="Label" parent="." groups=["inherited"]]

[node name="Cold" type="Node" parent="."]

[node name="Body" type="CharacterBody2D" parent="."]

[node name="Nav" type="NavigationRegion2D" parent="."]

[node name="Sparks" type="GPUParticles2D" parent="."]

[node name="Particles" type="GPUParticles2D" parent="."]
process_material = SubResource("ppm")

[node name="Tiles" type="TileMapLayer" parent="."]
tile_set = SubResource("ts")

[node name="Tiles2" type="TileMapLayer" parent="."]

[node name="Grid" type="GridMap" parent="."]
mesh_library = SubResource("lib")

[node name="Grid2" type="GridMap" parent="."]

[node name="Player" type="AnimationPlayer" parent="."]
libraries = {{
&"": SubResource("alib")
}}

[node name="BarePlayer" type="AnimationPlayer" parent="."]

[node name="Tree" type="AnimationTree" parent="."]
tree_root = SubResource("sm")

[node name="Blend" type="AnimationTree" parent="."]
tree_root = SubResource("bt")
""",
    f"{PREFIX}main.tscn": f"""[gd_scene format=3]

[ext_resource type="PackedScene" path="res://{PREFIX}inner.tscn" id="1"]

[node name="Main" type="Node2D"]

[node name="Relic" parent="." instance=ExtResource("1")]

[node name="Relic2" parent="." groups=["own_group"] instance=ExtResource("1")]

[node name="Own" type="Node" parent="."]

[editable path="Relic2"]
""",
    f"{PREFIX}ts.tres": f"""[gd_resource type="TileSet" format=3]

[ext_resource type="Texture2D" path="{TEX}" id="1"]

[sub_resource type="TileSetAtlasSource" id="src"]
texture = ExtResource("1")
0:0/0 = 0

[resource]
sources/0 = SubResource("src")
""",
    f"{PREFIX}alib.tres": """[gd_resource type="AnimationLibrary" format=3]

[sub_resource type="Animation" id="idle"]
length = 1.0

[resource]
_data = {
&"idle": SubResource("idle")
}
""",
    f"{PREFIX}base.tscn": """[gd_scene format=3]

[sub_resource type="Animation" id="idle"]
length = 1.0

[sub_resource type="AnimationLibrary" id="alib"]
_data = {
&"idle": SubResource("idle")
}

[node name="Base" type="Node2D"]

[node name="Label" type="Label" parent="." groups=["inherited"]]

[node name="Player" type="AnimationPlayer" parent="."]
libraries = {
&"": SubResource("alib")
}
""",
    f"{PREFIX}derived.tscn": f"""[gd_scene format=3]

[ext_resource type="PackedScene" path="res://{PREFIX}base.tscn" id="1"]
[ext_resource type="TileSet" path="res://{PREFIX}ts.tres" id="2"]
[ext_resource type="AnimationLibrary" path="res://{PREFIX}alib.tres" id="3"]

[node name="Derived" instance=ExtResource("1")]

[node name="Own" type="Node" parent="."]

[node name="OwnTiles" type="TileMapLayer" parent="."]
tile_set = ExtResource("2")

[node name="OwnPlayer" type="AnimationPlayer" parent="."]
libraries = {{
&"": ExtResource("3")
}}
""",
    # Reads the saved scenes back from disk, in a process that never saw the edits.
    f"{PREFIX}check.gd": f"""extends SceneTree

func _groups(node: Node) -> Array:
	var out := []
	for g in node.get_groups():
		if not str(g).begins_with("_"):
			out.append(str(g))
	out.sort()
	return out


func _children(node: Node) -> Array:
	var out := []
	for c in node.get_children():
		out.append(str(c.name))
	return out


func _has_tile(tile_set: TileSet, source: int) -> bool:
	if tile_set == null or not tile_set.has_source(source):
		return false
	return (tile_set.get_source(source) as TileSetAtlasSource).has_tile(Vector2i(1, 0))


func _tracks(player: Node, anim: String) -> int:
	var ap := player as AnimationPlayer
	return ap.get_animation(anim).get_track_count() if ap.has_animation(anim) else -1


func _items(grid: GridMap) -> Variant:
	return Array(grid.mesh_library.get_item_list()) if grid.mesh_library != null else null


func _instance(p: Node) -> Dictionary:
	var label: Label = p.get_node("Label")
	var tiles: TileMapLayer = p.get_node("Tiles")
	var tiles2: TileMapLayer = p.get_node("Tiles2")
	var grid: GridMap = p.get_node("Grid")
	var grid2: GridMap = p.get_node("Grid2")
	var player: AnimationPlayer = p.get_node("Player")
	var bare: AnimationPlayer = p.get_node("BarePlayer")
	var body: CharacterBody2D = p.get_node("Body")
	var sparks: GPUParticles2D = p.get_node("Sparks")
	var pm: ParticleProcessMaterial = p.get_node("Particles").process_material
	var src0: TileSetAtlasSource = tiles.tile_set.get_source(0)
	return {{
		"root_groups": _groups(p),
		"label_text": label.text,
		"label_groups": _groups(label),
		"font_color": label.has_theme_color_override("font_color"),
		"font_size": label.has_theme_font_size_override("font_size"),
		"stylebox": label.has_theme_stylebox_override("normal"),
		"script": label.get_script().resource_path if label.get_script() != null else "",
		"theme": label.theme != null,
		"floor_max_angle": snappedf(body.floor_max_angle, 0.001),
		"collision_layer": body.collision_layer,
		"navigation_layers": p.get_node("Nav").navigation_layers,
		"sparks_amount": sparks.amount,
		"sparks_material": sparks.process_material != null,
		"cold_children": p.get_node("Cold").get_child_count(),
		"cell_2_2": tiles.get_cell_source_id(Vector2i(2, 2)),
		"cell_4_4": tiles.get_cell_source_id(Vector2i(4, 4)),
		"tileset_source5": tiles.tile_set.has_source(5),
		"tile_1_0": src0.has_tile(Vector2i(1, 0)),
		"tiles2_tile": _has_tile(tiles2.tile_set, 1),
		"grid_cell": grid.get_cell_item(Vector3i(1, 0, 1)),
		"lib_items": _items(grid),
		"grid2_items": _items(grid2),
		"player_anims": Array(player.get_animation_list()),
		"idle_tracks": _tracks(player, "idle"),
		"bare_anims": Array(bare.get_animation_list()),
		"run_tracks": _tracks(bare, "run"),
		"state_probe": p.get_node("Tree").tree_root.has_node("Probe"),
		"blend_probe": p.get_node("Blend").tree_root.has_node("ProbeBlend"),
		"spread": pm.spread,
		"ramp": pm.color_ramp != null,
	}}


func _initialize() -> void:
	var main: Node = (load("{MAIN}") as PackedScene).instantiate()
	var derived: Node = (load("{DERIVED}") as PackedScene).instantiate()
	var own_tiles: TileMapLayer = derived.get_node("OwnTiles")
	var out := {{
		"Relic": _instance(main.get_node("Relic")),
		"Relic2": _instance(main.get_node("Relic2")),
		"main_children": _children(main),
		"own_tree_probe": (main.get_node("OwnTree") as AnimationTree).tree_root.has_node("Probe"),
		"derived": {{
			"children": _children(derived),
			"label_groups": _groups(derived.get_node("Label")),
			"base_idle_tracks": _tracks(derived.get_node("Player"), "idle"),
			"source5_tile": _has_tile(own_tiles.tile_set, 5),
			"source0_tile_1_0": _has_tile(own_tiles.tile_set, 0),
			"ext_idle_tracks": _tracks(derived.get_node("OwnPlayer"), "idle"),
		}},
	}}
	print("PERSIST_STATE " + JSON.stringify(out))
	main.free()
	derived.free()
	quit(0)
""",
}

Op = tuple[str, dict[str, Any], str | None]


def _instance_ops(p: str, reason: str | None) -> list[Op]:
    """Edits judged by the node rule alone — the same list for both instances."""
    label = f"{p}/Label"
    return [
        (
            "cmd_set_node_property",
            {"node_path": label, "property": "text", "value": "saved"},
            reason,
        ),
        ("cmd_add_to_group", {"node_path": label, "group": "extra"}, reason),
        ("cmd_add_to_group", {"node_path": label, "group": "inherited"}, reason),  # already in it
        (
            "cmd_set_theme_color",
            {"node_path": label, "name": "font_color", "color": "#ff0000"},
            reason,
        ),
        ("cmd_set_theme_font_size", {"node_path": label, "name": "font_size", "size": 21}, reason),
        ("cmd_set_theme_stylebox", {"node_path": label, "name": "normal"}, reason),
        ("cmd_create_theme", {"node_path": label}, reason),
        ("cmd_attach_script", {"node_path": label, "script_path": SCRIPT}, reason),
        (
            "cmd_setup_physics_body",
            {"node_path": f"{p}/Body", "properties": {"floor_max_angle": 0.5}},
            reason,
        ),
        ("cmd_set_physics_layers", {"node_path": f"{p}/Body", "layers": [2]}, reason),
        ("cmd_set_navigation_layers", {"node_path": f"{p}/Nav", "layers": [3]}, reason),
        ("cmd_apply_particle_preset", {"node_path": f"{p}/Sparks", "preset": "fire"}, reason),
        (
            "cmd_tilemap_set_cell",
            {"node_path": f"{p}/Tiles", "coords": [2, 2], "source_id": 0},
            reason,
        ),
        (
            "cmd_tilemap_fill_rect",
            {"node_path": f"{p}/Tiles", "rect": [4, 4, 2, 1], "source_id": 0},
            reason,
        ),
        (
            "cmd_gridmap_set_cell",
            {"node_path": f"{p}/Grid", "position": [1, 0, 1], "item": 0},
            reason,
        ),
        # resources created here have no path yet: they save (or not) with their node
        ("cmd_create_tileset", {"node_path": f"{p}/Tiles2"}, reason),
        (
            "cmd_add_tileset_atlas_source",
            {"node_path": f"{p}/Tiles2", "texture_path": TEX, "source_id": 1},
            reason,
        ),
        (
            "cmd_create_tile",
            {"node_path": f"{p}/Tiles2", "source_id": 1, "atlas_coords": [1, 0]},
            reason,
        ),
        ("cmd_tilemap_clear", {"node_path": f"{p}/Tiles2"}, reason),
        ("cmd_create_mesh_library", {"node_path": f"{p}/Grid2"}, reason),
        (
            "cmd_add_mesh_library_item",
            {"node_path": f"{p}/Grid2", "mesh_type": "BoxMesh", "item_id": 3},
            reason,
        ),
        ("cmd_create_animation", {"node_path": f"{p}/BarePlayer", "name": "run"}, reason),
        (
            "cmd_add_animation_track",
            {"node_path": f"{p}/BarePlayer", "animation": "run", "track_path": "Label:modulate"},
            reason,
        ),
    ]


MAIN_OPS: list[Op] = [
    *_instance_ops("Relic", NOT_EDITABLE),
    *_instance_ops("Relic2", None),
    # removing a group: the node rule first, then whether a scene it comes from defines it
    ("cmd_remove_from_group", {"node_path": "Relic/Label", "group": "inherited"}, NOT_EDITABLE),
    ("cmd_remove_from_group", {"node_path": "Relic2/Label", "group": "inherited"}, BASE_GROUP),
    ("cmd_remove_from_group", {"node_path": "Relic2", "group": "own_group"}, None),
    # resources embedded in the instanced scene are never re-saved, Editable Children or not
    (
        "cmd_add_tileset_atlas_source",
        {"node_path": "Relic2/Tiles", "texture_path": TEX, "source_id": 5},
        EMBEDDED,
    ),
    (
        "cmd_create_tile",
        {"node_path": "Relic2/Tiles", "source_id": 0, "atlas_coords": [1, 0]},
        EMBEDDED,
    ),
    (
        "cmd_add_mesh_library_item",
        {"node_path": "Relic2/Grid", "mesh_type": "BoxMesh", "item_id": 7},
        EMBEDDED,
    ),
    (
        "cmd_add_mesh_library_item",
        {"node_path": "Relic/Grid", "mesh_type": "BoxMesh", "item_id": 8},
        EMBEDDED,
    ),
    ("cmd_create_animation", {"node_path": "Relic2/Player", "name": "walk"}, EMBEDDED),
    (
        "cmd_add_animation_track",
        {"node_path": "Relic2/Player", "animation": "idle", "track_path": "Label:modulate"},
        EMBEDDED,
    ),
    (
        "cmd_insert_keyframe",
        {"node_path": "Relic2/Player", "animation": "idle", "track": 0, "time": 0.5, "value": 1.0},
        EMBEDDED,
    ),
    ("cmd_add_state_machine_state", {"tree_path": "Relic2/Tree", "state_name": "Probe"}, EMBEDDED),
    (
        "cmd_set_blend_tree_node",
        {"tree_path": "Relic2/Blend", "node_name": "ProbeBlend", "node_type": "AnimationNodeAdd2"},
        EMBEDDED,
    ),
    (
        "cmd_set_particle_material",
        {"node_path": "Relic2/Particles", "properties": {"spread": 33.0}},
        EMBEDDED,
    ),
    (
        "cmd_set_particle_color_gradient",
        {"node_path": "Relic2/Particles", "colors": ["#f00", "#00f"]},
        EMBEDDED,
    ),
    (
        "cmd_set_particle_material",
        {"node_path": "Relic/Particles", "properties": {"spread": 34.0}},
        EMBEDDED,
    ),
    # a node this scene owns, under a skipped instance child, is skipped with it
    ("cmd_create_node", {"parent_path": "Relic/Cold", "node_type": "Node", "name": "Extra"}, SETUP),
    ("cmd_rename_node", {"node_path": "Relic/Cold/Extra", "new_name": "Extra2"}, NOT_EDITABLE),
    ("cmd_rename_node", {"node_path": "Own", "new_name": "OwnRenamed"}, None),
    (
        "cmd_create_animation_tree",
        {"parent_path": ".", "name": "OwnTree", "root_type": "AnimationNodeStateMachine"},
        SETUP,
    ),
    ("cmd_add_state_machine_state", {"tree_path": "OwnTree", "state_name": "Probe"}, None),
]

DERIVED_OPS: list[Op] = [
    # an inherited scene diffs against its base exactly like an instance does
    ("cmd_remove_from_group", {"node_path": "Label", "group": "inherited"}, BASE_GROUP),
    ("cmd_add_to_group", {"node_path": "Label", "group": "extra"}, None),
    (
        "cmd_add_animation_track",
        {"node_path": "Player", "animation": "idle", "track_path": "Label:modulate"},
        EMBEDDED,
    ),
    # resource files: a new source (no path yet) in a TileSet file, a tile on it, a tile on a
    # source the file already had, and a track on an animation inside a library file
    (
        "cmd_add_tileset_atlas_source",
        {"node_path": "OwnTiles", "texture_path": TEX, "source_id": 5},
        None,
    ),
    ("cmd_create_tile", {"node_path": "OwnTiles", "source_id": 5, "atlas_coords": [1, 0]}, None),
    ("cmd_create_tile", {"node_path": "OwnTiles", "source_id": 0, "atlas_coords": [1, 0]}, None),
    (
        "cmd_add_animation_track",
        {"node_path": "OwnPlayer", "animation": "idle", "track_path": "Own:name"},
        None,
    ),
    ("cmd_rename_node", {"node_path": "Own", "new_name": "OwnRenamed"}, None),
]

# The instanced scene as authored: what a reload shows when nothing was saved.
AUTHORED: dict[str, Any] = {
    "root_groups": [],
    "label_text": "",
    "label_groups": ["inherited"],
    "font_color": False,
    "font_size": False,
    "stylebox": False,
    "script": "",
    "theme": False,
    "floor_max_angle": 0.785,
    "collision_layer": 1,
    "navigation_layers": 1,
    "sparks_amount": 8,
    "sparks_material": False,
    "cold_children": 0,
    "cell_2_2": -1,
    "cell_4_4": -1,
    "tileset_source5": False,
    "tile_1_0": False,
    "tiles2_tile": False,
    "grid_cell": -1,
    "lib_items": [0],
    "grid2_items": None,
    "player_anims": ["idle"],
    "idle_tracks": 0,
    "bare_anims": [],
    "run_tracks": -1,
    "state_probe": False,
    "blend_probe": False,
    "spread": 10.0,
    "ramp": False,
}
# Relic2 keeps every node-rule edit (and loses the own_group it removed); everything
# embedded in the instanced scene reads back as authored.
EDITABLE_SAVED = {
    **AUTHORED,
    "label_text": "saved",
    "label_groups": ["extra", "inherited"],
    "font_color": True,
    "font_size": True,
    "stylebox": True,
    "script": SCRIPT,
    "theme": True,
    "floor_max_angle": 0.5,
    "collision_layer": 2,
    "navigation_layers": 4,
    "sparks_amount": 32,
    "sparks_material": True,
    "cell_2_2": 0,
    "cell_4_4": 0,
    "tiles2_tile": True,
    "grid_cell": 0,
    "grid2_items": [3],
    "bare_anims": ["run"],
    "run_tracks": 1,
}


async def _open(bridge: Bridge, scene: str) -> None:
    response = await bridge.send("cmd_open_scene", {"scene_path": scene})
    assert response.ok, f"open {scene}: {response.error} {response.hint}"
    for _ in range(60):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("path") == scene:
            return
        await asyncio.sleep(0.25)
    raise AssertionError(f"{scene} did not become the active scene")


async def _apply(bridge: Bridge, ops: list[Op]) -> list[str]:
    """Run each op; return every verdict that differs from the expected one."""
    mismatches = []
    for command, params, reason in ops:
        response = await bridge.send(command, params)
        if not response.ok or response.result is None:
            mismatches.append(f"{command} {params}: failed {response.error} {response.hint}")
            continue
        result = response.result
        if reason == SETUP:
            continue
        if reason is None:
            if result.get("persisted") is not True or "reason" in result:
                mismatches.append(f"{command} {params}: expected persisted, got {result}")
        elif (
            result.get("persisted") is not False
            or result.get("reason") != reason
            or not result.get("hint")
        ):
            mismatches.append(f"{command} {params}: expected {reason}, got {result}")
    return mismatches


async def _run() -> list[str]:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    try:
        await _open(bridge, MAIN)
        mismatches = await _apply(bridge, MAIN_OPS)
        assert (await bridge.send("cmd_save_scene", {})).ok
        await _open(bridge, DERIVED)
        mismatches += await _apply(bridge, DERIVED_OPS)
        assert (await bridge.send("cmd_save_scene", {})).ok
        return mismatches
    finally:
        await bridge.close()


def _saved_state() -> dict[str, Any]:
    assert GODOT_BIN is not None
    run = subprocess.run(
        [
            GODOT_BIN,
            "--headless",
            "--path",
            str(GODOT_PROJECT),
            "--script",
            f"res://{PREFIX}check.gd",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    for line in run.stdout.splitlines():
        if line.startswith("PERSIST_STATE "):
            state: dict[str, Any] = json.loads(line.removeprefix("PERSIST_STATE "))
            return state
    raise AssertionError(
        f"reload check printed no state:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}"
    )


def test_live_persistence_verdicts_match_reload() -> None:
    assert GODOT_BIN is not None
    for name, text in FIXTURES.items():
        (GODOT_PROJECT / name).write_text(text)
    try:
        editor = subprocess.Popen(
            [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
        )
        try:
            mismatches = asyncio.run(_run())
        finally:
            editor.terminate()
            try:
                editor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                editor.kill()
        assert not mismatches, "verdicts that disagree with the expected save rule:\n" + "\n".join(
            mismatches
        )

        state = _saved_state()
        assert state["Relic"] == AUTHORED, "an edit to a non-editable instance child was saved"
        assert state["Relic2"] == EDITABLE_SAVED, "saved editable-instance state differs"
        assert "OwnRenamed" in state["main_children"] and "Own" not in state["main_children"]
        assert state["own_tree_probe"] is True, "a scene-owned AnimationTree root edit was lost"
        derived = state["derived"]
        assert derived["label_groups"] == ["extra", "inherited"]
        assert derived["base_idle_tracks"] == 0, "an edit to the base scene's library was saved"
        assert derived["source5_tile"] is True, "a new source in a TileSet file was lost"
        assert derived["source0_tile_1_0"] is True, "a tile in a TileSet file was lost"
        assert derived["ext_idle_tracks"] == 1, "a track in an AnimationLibrary file was lost"
        assert "OwnRenamed" in derived["children"] and "Own" not in derived["children"]
    finally:
        for leftover in GODOT_PROJECT.glob(f"{PREFIX}*"):
            leftover.unlink(missing_ok=True)
