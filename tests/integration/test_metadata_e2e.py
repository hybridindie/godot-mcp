"""E2E: text-scene metadata is exposed and survives an editor mutation (#600).

Godot 4.8 serializes scene-level metadata as ``[resource]`` ``metadata/...``
properties in ``.tscn``. This boots a headless editor with a fixture scene that
carries metadata, asserts the inspection surface reports it, mutates the scene,
saves, and confirms the metadata survived the round-trip.

Engine-gated: on 4.4–4.7 the text-scene format has no metadata support, so the
test skips (a genuine engine precondition, not a suite-health skip).
"""

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
    engine_at_least,
    serve_and_await_editor,
    wait_for_active_scene,
)

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    pytest.mark.skipif(not engine_at_least(4, 8), reason="scene metadata is Godot 4.8+"),
]

BRIDGE_URL = e2e_bridge_url()
SCENE = "res://__meta_roundtrip.tscn"
SCENE_FILE = GODOT_PROJECT / "__meta_roundtrip.tscn"

# The 4.8 text-scene form: a [resource] section carrying metadata/... entries,
# written only when the scene has metadata (godotengine/godot#121920).
FIXTURE = """[gd_scene load_steps=1 format=3]

[resource]
metadata/author = "e2e"
metadata/tier = 3

[node name="Root" type="Node2D"]
"""


async def _ok(bridge: Bridge, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = await bridge.send(command, params or {})
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _run_roundtrip() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")
    try:
        await _ok(bridge, "cmd_open_scene", {"scene_path": SCENE})
        await wait_for_active_scene(bridge, SCENE)

        active = await _ok(bridge, "cmd_get_active_scene")
        assert active["metadata"] == {"author": "e2e", "tier": 3}, active

        tree = await _ok(bridge, "cmd_get_scene_tree")
        assert tree["metadata"] == {"author": "e2e", "tier": 3}, tree

        # Mutate the scene, save, and confirm the metadata survived the rewrite.
        await _ok(
            bridge,
            "cmd_create_node",
            {"parent_path": ".", "node_type": "Node2D", "name": "Child"},
        )
        await _ok(bridge, "cmd_save_all_scenes")

        saved = SCENE_FILE.read_text(encoding="utf-8")
        assert "metadata/author" in saved and "metadata/tier" in saved, saved
        assert "e2e" in saved, saved
        assert '[node name="Child"' in saved, saved
    finally:
        await bridge.close()


def test_scene_metadata_roundtrips_through_editor_save() -> None:
    assert GODOT_BIN is not None
    SCENE_FILE.write_text(FIXTURE, encoding="utf-8")
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run_roundtrip())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        for suffix in ("", ".uid"):
            (GODOT_PROJECT / f"__meta_roundtrip.tscn{suffix}").unlink(missing_ok=True)
