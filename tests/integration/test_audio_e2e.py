"""End-to-end audio test against a live editor (issue #44).

Note: the bus tools mutate the global AudioServer layout. This test spawns its own
headless editor (torn down afterwards), so the bus changes don't leak between runs.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"
SCRATCH = "res://tmp_e2e_audio.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_audio.tscn"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("is_open"):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("scene did not open")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    for _ in range(60):
        try:
            await bridge.connect()
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        raise AssertionError("could not connect to the addon bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)

        # add a bus, then route a player to it and attach an effect
        bus = await _ok(bridge, "cmd_add_audio_bus", {"name": "Music", "volume_db": -3.0})
        assert bus["name"] == "Music" and bus["index"] >= 1
        player = await _ok(
            bridge,
            "cmd_add_audio_player",
            {
                "parent_path": ".",
                "player_type": "AudioStreamPlayer2D",
                "name": "SFX",
                "properties": {"volume_db": -6.0, "bus": "Music"},
            },
        )
        assert player["node_path"] == "SFX" and player["player_type"] == "AudioStreamPlayer2D"
        tree = await _ok(bridge, "cmd_get_scene_tree", {})
        assert any(
            c["name"] == "SFX" and c["type"] == "AudioStreamPlayer2D"
            for c in tree["tree"]["children"]
        )
        effect = await _ok(
            bridge,
            "cmd_add_audio_bus_effect",
            {"bus": "Music", "effect_type": "AudioEffectReverb", "properties": {"wet": 0.5}},
        )
        assert effect["effect_type"] == "AudioEffectReverb" and effect["effect_index"] == 0

        # the read-only layout reflects the new bus + its effect
        layout = await _ok(bridge, "cmd_get_audio_bus_layout", {})
        music = next(b for b in layout["buses"] if b["name"] == "Music")
        assert abs(music["volume_db"] - (-3.0)) < 0.01
        assert any(e["type"] == "AudioEffectReverb" for e in music["effects"])

        # G8 (#219): remove the effect, then the bus — confirm each via the layout.
        removed_effect = await _ok(
            bridge,
            "cmd_remove_audio_bus_effect",
            {"bus": "Music", "effect_index": 0, "confirm": True},
        )
        assert removed_effect["removed"] is True and removed_effect["effect_index"] == 0
        layout2 = await _ok(bridge, "cmd_get_audio_bus_layout", {})
        music2 = next(b for b in layout2["buses"] if b["name"] == "Music")
        assert not any(e["type"] == "AudioEffectReverb" for e in music2["effects"])

        removed_bus = await _ok(bridge, "cmd_remove_audio_bus", {"bus": "Music", "confirm": True})
        assert removed_bus["removed"] is True and removed_bus["name"] == "Music"
        layout3 = await _ok(bridge, "cmd_get_audio_bus_layout", {})
        assert not any(b["name"] == "Music" for b in layout3["buses"])

        # the Master bus is never removable; a bad effect index is rejected
        master = await bridge.send("cmd_remove_audio_bus", {"bus": "Master", "confirm": True})
        assert master.ok is False and master.error == "VALIDATION_ERROR"
        bad_idx = await bridge.send(
            "cmd_remove_audio_bus_effect",
            {"bus": "Master", "effect_index": 99, "confirm": True},
        )
        assert bad_idx.ok is False and bad_idx.error == "VALIDATION_ERROR"

        # validation: bad player type, duplicate bus, unknown bus, bad effect type, bad stream
        bad_player = await bridge.send(
            "cmd_add_audio_player", {"parent_path": ".", "player_type": "Node2D"}
        )
        assert bad_player.ok is False and bad_player.error == "VALIDATION_ERROR"
        dup_bus = await bridge.send("cmd_add_audio_bus", {"name": "Music"})
        assert dup_bus.ok is False and dup_bus.error == "VALIDATION_ERROR"
        unknown_bus = await bridge.send(
            "cmd_add_audio_bus_effect", {"bus": "Nope", "effect_type": "AudioEffectReverb"}
        )
        assert unknown_bus.ok is False and unknown_bus.error == "VALIDATION_ERROR"
        bad_effect = await bridge.send(
            "cmd_add_audio_bus_effect", {"bus": "Music", "effect_type": "Node"}
        )
        assert bad_effect.ok is False and bad_effect.error == "VALIDATION_ERROR"
        bad_stream = await bridge.send(
            "cmd_add_audio_player",
            {
                "parent_path": ".",
                "player_type": "AudioStreamPlayer",
                "stream_path": "res://nope.ogg",
            },
        )
        assert bad_stream.ok is False and bad_stream.error == "RESOURCE_NOT_FOUND"
    finally:
        await bridge.close()


def test_live_audio() -> None:
    assert GODOT_BIN is not None
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
