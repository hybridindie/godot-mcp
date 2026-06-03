"""End-to-end export test against a live editor (issue #50).

Verifies the addon parses a real export_presets.cfg via Godot's ConfigFile. Running an
actual export (export_project) needs export templates installed for the target platform,
so that path is exercised by the contract test with a fake runner, not here.
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
PRESETS_FILE = GODOT_PROJECT / "export_presets.cfg"
_PRESETS_CONTENT = (
    "[preset.0]\n"
    'name="Linux/X11"\n'
    'platform="Linux/X11"\n'
    "runnable=true\n"
    'export_path="build/game.x86_64"\n'
    "[preset.0.options]\n"
    "binary_format/embed_pck=false\n"
)


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


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
        presets = await _ok(bridge, "cmd_list_export_presets", {})
        assert presets["has_config"] is True
        linux = next(p for p in presets["presets"] if p["name"] == "Linux/X11")
        assert linux["platform"] == "Linux/X11"
        assert linux["runnable"] is True
        assert linux["export_path"] == "build/game.x86_64"
        assert linux["index"] == 0

        info = await _ok(bridge, "cmd_get_export_info", {})
        assert info["has_config"] is True
        assert info["preset_count"] == 1
        assert "Linux/X11" in info["preset_names"]
    finally:
        await bridge.close()


def test_live_export_presets() -> None:
    assert GODOT_BIN is not None
    # Preserve any pre-existing export config rather than destroying it.
    prior = PRESETS_FILE.read_bytes() if PRESETS_FILE.exists() else None
    PRESETS_FILE.write_text(_PRESETS_CONTENT, encoding="utf-8")
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
        if prior is None:
            PRESETS_FILE.unlink(missing_ok=True)
        else:
            PRESETS_FILE.write_bytes(prior)
