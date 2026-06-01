"""End-to-end script tools test: live editor + real parse check (issue #10).

Drives the addon script handlers over the bridge (write/read/patch, with UndoRedo +
filesystem rescan) against a live editor, and validates structured parse errors via
a real ``godot --check-only`` run. Skipped without Godot.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig, ServerConfig
from mcp_server.runtime import GodotRunner
from mcp_server.tools.scripts import parse_check_errors
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

BRIDGE_URL = "ws://localhost:9080"
VALID = "res://tmp_e2e_script.gd"
BROKEN = "res://tmp_e2e_broken.gd"
_ARTIFACTS = [
    "tmp_e2e_script.gd",
    "tmp_e2e_script.gd.uid",
    "tmp_e2e_broken.gd",
    "tmp_e2e_broken.gd.uid",
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

    runner = GodotRunner(ServerConfig(godot_bin=GODOT_BIN))
    try:
        # write → read round-trip
        written = await _ok(
            bridge,
            "cmd_write_script",
            {"script_path": VALID, "content": 'extends Node\nfunc _ready():\n\tprint("hi")\n'},
        )
        assert written["created"] is True
        read = await _ok(bridge, "cmd_read_script", {"script_path": VALID})
        assert 'print("hi")' in read["content"]

        # patch
        patched = await _ok(
            bridge, "cmd_patch_script", {"script_path": VALID, "find": "hi", "replace": "bye"}
        )
        assert patched["replacements"] == 1
        after = await _ok(bridge, "cmd_read_script", {"script_path": VALID})
        assert 'print("bye")' in after["content"]

        # the valid (patched) script parses cleanly
        good = await runner.check_script(str(GODOT_PROJECT), VALID, timeout=60.0)
        assert parse_check_errors(good.stdout + "\n" + good.stderr) == []

        # a broken script yields a structured parse error with a line number
        broken_src = "extends Node\nvar x =\n"
        await _ok(bridge, "cmd_write_script", {"script_path": BROKEN, "content": broken_src})
        bad = await runner.check_script(str(GODOT_PROJECT), BROKEN, timeout=60.0)
        errors = parse_check_errors(bad.stdout + "\n" + bad.stderr)
        assert errors and errors[0].line is not None
    finally:
        await bridge.close()


def test_live_script_workflow() -> None:
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
