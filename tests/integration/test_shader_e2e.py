"""End-to-end shader test against a live editor (issue #47)."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, serve_and_await_editor

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://127.0.0.1:9097"
SCRATCH = "res://tmp_e2e_shader.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_shader.tscn"
SHADER_PATH = "res://tmp_e2e_shader.gdshader"
SHADER_FILE = GODOT_PROJECT / "tmp_e2e_shader.gdshader"
SHADER_UID_FILE = GODOT_PROJECT / "tmp_e2e_shader.gdshader.uid"  # Godot 4.4+ sidecar

# #458: an instanced scene placed twice — "Relic" without Editable Children, "Relic2" with —
# plus scene-owned nodes carrying an external (.tres) and an embedded material. "Shell"/"Shell2"
# nest that scene one level deeper (Mid -> Core): editable at the outer level only, and at both.
PERSIST_GLOW = GODOT_PROJECT / "tmp_e2e_persist_glow.gdshader"
PERSIST_MAT = GODOT_PROJECT / "tmp_e2e_persist_mat.tres"
PERSIST_MAT_INNER = GODOT_PROJECT / "tmp_e2e_persist_mat_inner.tres"
PERSIST_INNER = GODOT_PROJECT / "tmp_e2e_persist_inner.tscn"
PERSIST_MID = GODOT_PROJECT / "tmp_e2e_persist_mid.tscn"
PERSIST_MAIN = GODOT_PROJECT / "tmp_e2e_persist_main.tscn"
PERSIST_FIXTURES = {
    PERSIST_GLOW: (
        "shader_type spatial;\nuniform float pulse_speed = 1.0;\n"
        "void fragment() {\n\tALBEDO = vec3(pulse_speed);\n}\n"
    ),
    PERSIST_MAT: """[gd_resource type="ShaderMaterial" format=3]

[ext_resource type="Shader" path="res://tmp_e2e_persist_glow.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/pulse_speed = 1.0
""",
    PERSIST_MAT_INNER: """[gd_resource type="ShaderMaterial" format=3]

[ext_resource type="Shader" path="res://tmp_e2e_persist_glow.gdshader" id="1"]

[resource]
shader = ExtResource("1")
shader_parameter/pulse_speed = 1.0
""",
    PERSIST_INNER: """[gd_scene format=3]

[ext_resource type="Shader" path="res://tmp_e2e_persist_glow.gdshader" id="1"]
[ext_resource type="ShaderMaterial" path="res://tmp_e2e_persist_mat_inner.tres" id="2"]

[sub_resource type="ShaderMaterial" id="ShaderMaterial_inner"]
shader = ExtResource("1")
shader_parameter/pulse_speed = 1.0

[node name="Inner" type="Node3D"]

[node name="Orb" type="MeshInstance3D" parent="."]
material_override = SubResource("ShaderMaterial_inner")

[node name="Plain" type="MeshInstance3D" parent="."]

[node name="ExtOrb" type="MeshInstance3D" parent="."]
material_override = ExtResource("2")
""",
    PERSIST_MID: """[gd_scene format=3]

[ext_resource type="PackedScene" path="res://tmp_e2e_persist_inner.tscn" id="1"]

[node name="Mid" type="Node3D"]

[node name="Core" parent="." instance=ExtResource("1")]
""",
    PERSIST_MAIN: """[gd_scene format=3]

[ext_resource type="PackedScene" path="res://tmp_e2e_persist_inner.tscn" id="1"]
[ext_resource type="Shader" path="res://tmp_e2e_persist_glow.gdshader" id="2"]
[ext_resource type="ShaderMaterial" path="res://tmp_e2e_persist_mat.tres" id="3"]
[ext_resource type="PackedScene" path="res://tmp_e2e_persist_mid.tscn" id="4"]

[sub_resource type="ShaderMaterial" id="ShaderMaterial_main"]
shader = ExtResource("2")
shader_parameter/pulse_speed = 1.0

[node name="Main" type="Node3D"]

[node name="Relic" parent="." instance=ExtResource("1")]

[node name="Relic2" parent="." instance=ExtResource("1")]

[node name="OwnExt" type="MeshInstance3D" parent="."]
material_override = ExtResource("3")

[node name="OwnEmbedded" type="MeshInstance3D" parent="."]
material_override = SubResource("ShaderMaterial_main")

[node name="Shell" parent="." instance=ExtResource("4")]

[node name="Shell2" parent="." instance=ExtResource("4")]

[editable path="Relic2"]
[editable path="Shell"]
[editable path="Shell2"]
[editable path="Shell2/Core"]
""",
}

SHADER_CODE = (
    "shader_type canvas_item;\n"
    "uniform float strength = 1.0;\n"
    "void fragment() {\n\tCOLOR = vec4(strength);\n}\n"
)


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _create(bridge: Bridge, name: str, node_type: str, parent: str = ".") -> None:
    await _ok(
        bridge, "cmd_create_node", {"parent_path": parent, "node_type": node_type, "name": name}
    )


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("is_open"):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("scene did not open")


async def _check_persistence(bridge: Bridge) -> None:
    """#458/#415: every reported ``persisted`` flag must match what the editor writes."""
    main_path = "res://tmp_e2e_persist_main.tscn"
    await _ok(bridge, "cmd_open_scene", {"scene_path": main_path})
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("path") == main_path:
            break
        await asyncio.sleep(0.25)
    else:
        raise AssertionError("persistence fixture scene did not become active")

    glow = "res://tmp_e2e_persist_glow.gdshader"

    async def assign(node_path: str) -> dict[str, Any]:
        return await _ok(
            bridge, "cmd_assign_shader_material", {"node_path": node_path, "shader_path": glow}
        )

    async def set_param(node_path: str, value: float) -> dict[str, Any]:
        return await _ok(
            bridge,
            "cmd_set_shader_param",
            {"node_path": node_path, "name": "pulse_speed", "value": value, "param_type": "float"},
        )

    def assert_not_persisted(result: dict[str, Any], reason: str) -> None:
        assert result["persisted"] is False, result
        assert result["reason"] == reason, result
        assert result["hint"], result

    # the #415 repro: applied live, but the instance has no Editable Children
    assert_not_persisted(await assign("Relic/Plain"), "instanced_child_not_editable")
    assert_not_persisted(await set_param("Relic/Plain", 4.0), "instanced_child_not_editable")
    # Editable Children on -> the override and its fresh material are scene-owned
    editable = await assign("Relic2/Plain")
    assert editable["persisted"] is True and "reason" not in editable, editable
    assert (await set_param("Relic2/Plain", 6.0))["persisted"] is True
    # a material embedded in the instanced scene file never saves with this scene
    assert_not_persisted(await set_param("Relic2/Orb", 7.0), "embedded_in_other_resource")
    assert_not_persisted(await set_param("Relic/Orb", 8.0), "embedded_in_other_resource")
    # external .tres (saved alongside the scene) and a material this scene embeds
    assert (await set_param("OwnExt", 9.0))["persisted"] is True
    assert (await set_param("OwnEmbedded", 5.0))["persisted"] is True
    # the edit lands in the .tres, which the editor saves even though the node is skipped
    assert (await set_param("Relic/ExtOrb", 2.5))["persisted"] is True
    # scene-owned nodes created under an instanced child: the packer never visits the
    # subtree of a skipped node, so the whole parent path decides
    await _create(bridge, "Extra", "MeshInstance3D", parent="Relic/Plain")
    assert_not_persisted(await assign("Relic/Plain/Extra"), "instanced_child_not_editable")
    await _create(bridge, "Extra", "MeshInstance3D", parent="Relic2/Plain")
    assert (await assign("Relic2/Plain/Extra"))["persisted"] is True
    # nested instances: Editable Children on the outer instance does not reach the instance
    # inside it — the root stores a flag per level ("Shell2/Core") and every level needs one
    assert_not_persisted(await assign("Shell/Core/Plain"), "instanced_child_not_editable")
    assert (await assign("Shell2/Core/Plain"))["persisted"] is True

    await _ok(bridge, "cmd_save_scene", {})
    main_text = PERSIST_MAIN.read_text()
    inner_text = PERSIST_INNER.read_text()
    assert 'parent="Relic"' not in main_text, "non-editable instance override was saved"
    assert 'parent="Relic/Plain"' not in main_text, "node under a skipped instance child saved"
    assert 'name="Extra" type="MeshInstance3D" parent="Relic2/Plain"' in main_text
    assert "pulse_speed = 6.0" in main_text and "pulse_speed = 5.0" in main_text
    assert "pulse_speed = 7.0" not in main_text + inner_text
    assert "pulse_speed = 8.0" not in main_text + inner_text
    assert "pulse_speed = 4.0" not in main_text
    assert "pulse_speed = 9.0" in PERSIST_MAT.read_text()
    assert "pulse_speed = 2.5" in PERSIST_MAT_INNER.read_text()
    assert 'parent="Shell/Core' not in main_text, "override in a non-editable nested instance saved"
    assert 'parent="Shell2/Core"' in main_text, "override in an editable nested instance lost"


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # create + read the shader file
        created = await _ok(
            bridge, "cmd_create_shader", {"shader_path": SHADER_PATH, "code": SHADER_CODE}
        )
        assert created["created"] is True
        assert SHADER_FILE.exists(), "shader should be written to disk"
        read = await _ok(bridge, "cmd_read_shader", {"shader_path": SHADER_PATH})
        assert "uniform float strength" in read["code"]

        # assign to a 2D node -> material, and a 3D node -> material_override
        await _create(bridge, "Sprite", "Sprite2D")
        assigned = await _ok(
            bridge,
            "cmd_assign_shader_material",
            {"node_path": "Sprite", "shader_path": SHADER_PATH},
        )
        assert assigned["material_property"] == "material"
        await _create(bridge, "Mesh", "MeshInstance3D")
        assigned3d = await _ok(
            bridge,
            "cmd_assign_shader_material",
            {"node_path": "Mesh", "shader_path": SHADER_PATH},
        )
        assert assigned3d["material_property"] == "material_override"

        # set a uniform parameter on the assigned ShaderMaterial
        param = await _ok(
            bridge,
            "cmd_set_shader_param",
            {"node_path": "Sprite", "name": "strength", "value": 0.5, "param_type": "float"},
        )
        assert param["name"] == "strength"

        # validation: no material slot, no ShaderMaterial yet, bad paths
        await _create(bridge, "Plain", "Node")
        no_slot = await bridge.send(
            "cmd_assign_shader_material", {"node_path": "Plain", "shader_path": SHADER_PATH}
        )
        assert no_slot.ok is False and no_slot.error == "VALIDATION_ERROR"
        no_material = await bridge.send(
            "cmd_set_shader_param",
            {"node_path": "Mesh", "name": "x", "value": 1, "param_type": "int"},
        )
        # Mesh has a ShaderMaterial (assigned above) -> this should succeed
        assert no_material.ok is True
        await _create(bridge, "Bare", "Sprite2D")
        bare = await bridge.send(
            "cmd_set_shader_param", {"node_path": "Bare", "name": "x", "value": 1}
        )
        assert bare.ok is False and bare.error == "VALIDATION_ERROR"
        bad_create = await bridge.send(
            "cmd_create_shader", {"shader_path": "res://x.txt", "code": "x"}
        )
        assert bad_create.ok is False and bad_create.error == "VALIDATION_ERROR"
        missing = await bridge.send("cmd_read_shader", {"shader_path": "res://nope.gdshader"})
        assert missing.ok is False and missing.error == "RESOURCE_NOT_FOUND"
        bad_shader = await bridge.send(
            "cmd_assign_shader_material",
            {"node_path": "Sprite", "shader_path": "res://nope.gdshader"},
        )
        assert bad_shader.ok is False and bad_shader.error == "RESOURCE_NOT_FOUND"

        await _check_persistence(bridge)
    finally:
        await bridge.close()


def test_live_shader() -> None:
    assert GODOT_BIN is not None
    for fixture, text in PERSIST_FIXTURES.items():
        fixture.write_text(text)
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        SCRATCH_FILE.unlink(missing_ok=True)
        SHADER_FILE.unlink(missing_ok=True)
        SHADER_UID_FILE.unlink(missing_ok=True)
        for leftover in GODOT_PROJECT.glob("tmp_e2e_persist_*"):
            leftover.unlink(missing_ok=True)
