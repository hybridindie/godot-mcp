"""End-to-end asset import test against a live editor (issue #108).

Imports a local file, checks its import status, and creates a material from
texture resources. Skipped without Godot.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"
IMPORTED_PNG = "res://tmp_e2e_import.png"
ALBEDO_TEX = "res://tmp_e2e_albedo.tres"
MATERIAL = "res://tmp_e2e_material.tres"
_ARTIFACTS = [
    "tmp_e2e_import.png",
    "tmp_e2e_import.png.import",
    "tmp_e2e_albedo.tres",
    "tmp_e2e_material.tres",
]


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
        # Import a real file from outside the project into res://.
        external_png = Path(__file__).with_name("_test_pixel.png")
        external_png.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        imported = await _ok(
            bridge,
            "cmd_import_asset",
            {
                "source": str(external_png),
                "target_path": IMPORTED_PNG,
                "overwrite": True,
            },
        )
        assert imported["imported"] is True
        assert imported["target_path"] == IMPORTED_PNG
        assert imported["detected_type"] == "Texture2D"

        # Check import status.
        status = await _ok(bridge, "cmd_get_import_status", {"target_path": IMPORTED_PNG})
        assert status["imported"] is True
        # Godot imports a PNG as a CompressedTexture2D (a Texture2D subtype); accept
        # either the base or the concrete imported type.
        assert (status.get("type") or "").endswith("Texture2D")

        # Create a texture resource to use as material input.
        await _ok(
            bridge,
            "cmd_create_resource",
            {"type": "GradientTexture2D", "resource_path": ALBEDO_TEX},
        )

        # Create a material from that texture.
        mat = await _ok(
            bridge,
            "cmd_create_material_from_textures",
            {"albedo": ALBEDO_TEX, "path": MATERIAL},
        )
        assert mat["created"] is True
        assert mat["material_path"] == MATERIAL
        assert "albedo" in mat["channels_set"]
    finally:
        await bridge.close()
        external_png.unlink(missing_ok=True)


def test_live_asset_import_workflow() -> None:
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
        for name in _ARTIFACTS:
            (GODOT_PROJECT / name).unlink(missing_ok=True)
