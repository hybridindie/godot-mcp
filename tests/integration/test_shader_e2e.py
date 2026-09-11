"""End-to-end shader test against a live editor (issue #47)."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    serve_and_await_editor,
)

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

# Ephemeral per-run port (issue #444): no fixed port, so a concurrent
# job's (or an orphaned) editor can never connect to this test's listener.
BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_shader.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_shader.tscn"
SHADER_PATH = "res://tmp_e2e_shader.gdshader"
SHADER_FILE = GODOT_PROJECT / "tmp_e2e_shader.gdshader"
SHADER_UID_FILE = GODOT_PROJECT / "tmp_e2e_shader.gdshader.uid"  # Godot 4.4+ sidecar
BLANK = "res://tmp_e2e_blank_material.tres"  # a ShaderMaterial with no shader (#465)
BLANK_FILES = [
    GODOT_PROJECT / "tmp_e2e_blank_material.tres",
    GODOT_PROJECT / "tmp_e2e_blank_material.tres.uid",
]

SHADER_CODE = (
    "shader_type canvas_item;\n"
    "uniform float strength = 1.0;\n"
    "uniform vec4 tint_array;\n"
    "uniform vec4 tint_dict;\n"
    "uniform vec4 tint_inferred;\n"
    "uniform vec4 tint_string;\n"
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

        # #465: read the uniform back (set on the 2D material, unset on the 3D one) and a
        # name the shader does not declare
        got = await _ok(bridge, "cmd_get_shader_param", {"node_path": "Sprite", "name": "strength"})
        assert got["exists"] is True and got["value"] == 0.5, got
        unset = await _ok(bridge, "cmd_get_shader_param", {"node_path": "Mesh", "name": "strength"})
        # declared but never set on this material: Godot reports no value (the shader's
        # own default applies), and neither ShaderMaterial nor RenderingServer exposes it
        assert unset["exists"] is True and unset["value"] is None, unset
        undeclared = await _ok(
            bridge, "cmd_get_shader_param", {"node_path": "Sprite", "name": "no_such_uniform"}
        )
        assert undeclared["exists"] is False and undeclared["value"] is None, undeclared
        # a ShaderMaterial with no shader declares nothing: exists false, not a script error
        await _ok(bridge, "cmd_create_resource", {"type": "ShaderMaterial", "resource_path": BLANK})
        await _create(bridge, "Shaderless", "Sprite2D")
        await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Shaderless", "property": "material", "value": BLANK},
        )
        blank = await _ok(
            bridge, "cmd_get_shader_param", {"node_path": "Shaderless", "name": "strength"}
        )
        assert blank["exists"] is False and blank["value"] is None, blank
        # #464: vec4 uniforms, one per accepted input shape; the saved scene is the truth
        vec4_sets: list[tuple[str, Any, str]] = [
            ("tint_array", [1, 0.5, 0.25, 1], "vector4"),
            ("tint_dict", {"x": 0.1, "y": 0.2, "z": 0.3, "w": 0.4}, "vector4"),
            ("tint_inferred", [2, 3, 4, 5], ""),
            ("tint_string", "Vector4(6, 7, 8, 9)", "vector4"),
        ]
        for uniform, value, param_type in vec4_sets:
            await _ok(
                bridge,
                "cmd_set_shader_param",
                {"node_path": "Sprite", "name": uniform, "value": value, "param_type": param_type},
            )
        await _ok(bridge, "cmd_save_scene", {})
        saved = SCRATCH_FILE.read_text()
        assert "shader_parameter/tint_array = Vector4(1, 0.5, 0.25, 1)" in saved, saved
        assert "shader_parameter/tint_dict = Vector4(0.1, 0.2, 0.3, 0.4)" in saved, saved
        assert "shader_parameter/tint_inferred = Vector4(2, 3, 4, 5)" in saved, saved
        assert "shader_parameter/tint_string = Vector4(6, 7, 8, 9)" in saved, saved

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
    finally:
        await bridge.close()


def test_live_shader() -> None:
    assert GODOT_BIN is not None
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
        for path in BLANK_FILES:
            path.unlink(missing_ok=True)
