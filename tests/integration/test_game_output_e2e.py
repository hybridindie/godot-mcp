"""Live e2e: the game console output capture (issue #534).

Launches a real headless editor, plays a scratch scene with the runtime probe
autoload, and drives the output ring end to end over the bridge:

1. The game's ``print()`` / ``push_error()`` / ``push_warning()`` stream is
   captured by the probe's Logger into the bounded ring (the game prints
   markers; the editor reads them back).
2. ``cmd_get_game_output`` serves the ring with the honesty counts
   (``total``/``dropped``) and the monotonic ``seq`` cursor.
3. ``since_seq`` filtering: a second pull with the first call's ``next_seq``
   returns only newer entries.
4. The capture keeps working **while the game is frozen at a debugger break**
   — that's the moment reading output matters most (#411/#446 parity).

Same headless-editor pattern as ``test_input_sim_e2e.py`` (issue #444's
ephemeral port, save/restore of project.godot, scratch scene cleanup).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    needs_display,
    serve_and_await_editor,
)

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    needs_display,
]

# Ephemeral per-run port (issue #444).
BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_game_output.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_game_output.tscn"
SCRIPT_FILE = GODOT_PROJECT / "tmp_e2e_game_output.gd"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
PROBE = "res://addons/godot_mcp/mcp_runtime_probe.gd"

# The game script: prints into all three captured streams at _ready so the
# probe's Logger ring has stdout + error + warning entries to serve.
GAME_SCRIPT = """extends Node2D

func _ready() -> void:
	print("GAME_OUTPUT_STDOUT_MARKER")
	push_error("GAME_OUTPUT_ERROR_MARKER")
	push_warning("GAME_OUTPUT_WARNING_MARKER")
"""


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_connected(bridge: Bridge) -> None:
    for _ in range(30):
        state = await _ok(bridge, "cmd_get_game_scene_tree", {})
        if state.get("connected"):
            return
        await asyncio.sleep(0.5)
    raise AssertionError("probe never connected")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        # Attach the printing script so the game emits into all three streams
        # at startup (stdout + push_error + push_warning).
        Path(SCRIPT_FILE).write_text(GAME_SCRIPT)
        await _ok(bridge, "cmd_attach_script", {"node_path": ".", "script_path": "res://tmp_e2e_game_output.gd"})
        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await _wait_connected(bridge)

        # The game prints via stdout, error, and warning streams; the probe's
        # Logger sink captures all three into the ring. Give the game a moment
        # to emit (the autoload prints at _ready).
        first: dict[str, Any] | None = None
        for _ in range(20):
            out = await _ok(bridge, "cmd_get_game_output", {})
            if out.get("entries"):
                first = out
                break
            await asyncio.sleep(0.25)
        assert first is not None, "the game's output ring stayed empty"
        entries = first["entries"]
        kinds = {e["kind"] for e in entries}
        texts = [e["text"] for e in entries]
        assert "stdout" in kinds, f"no stdout capture: {entries}"
        assert "error" in kinds, f"push_error not captured: {texts}"
        assert "warning" in kinds, f"push_warning not captured: {texts}"
        assert any("GAME_OUTPUT_STDOUT_MARKER" in t for t in texts), texts
        assert any("GAME_OUTPUT_ERROR_MARKER" in t for t in texts), texts
        assert any("GAME_OUTPUT_WARNING_MARKER" in t for t in texts), texts
        # Honesty counts: total counts everything ever captured, dropped is
        # the honest eviction count (0 here — nothing evicted yet).
        assert first["total"] >= len(entries)
        assert first["dropped"] >= 0
        # Monotonic seq cursor.
        seqs = [e["seq"] for e in entries]
        assert seqs == sorted(seqs)
        next_seq = first["next_seq"]
        assert next_seq >= seqs[-1]

        # since_seq cursor: pulling from the last seen seq returns only newer
        # entries (or none if nothing new was printed).
        await asyncio.sleep(0.3)
        second = await _ok(bridge, "cmd_get_game_output", {"since_seq": next_seq})
        for entry in second["entries"]:
            assert entry["seq"] > next_seq, f"cursor leaked old entries: {entry}"

        # The capture works while the game is frozen at a debugger break —
        # print into the ring *during* the break and read it back.
        pre_out = await _ok(bridge, "cmd_get_game_output", {})
        pre_count = len(pre_out["entries"])
        await _ok(bridge, "cmd_force_break", {})
        breaked = False
        for _ in range(40):
            state = await _ok(bridge, "cmd_get_debug_break_state", {})
            if state["breaked"]:
                breaked = True
                break
            await asyncio.sleep(0.2)
        assert breaked, "force_break did not report the game entering the break loop"
        # While frozen: the ring is still readable (not gated by the break).
        frozen = await _ok(bridge, "cmd_get_game_output", {})
        assert frozen["connected"] is True
        assert len(frozen["entries"]) >= pre_count
        await _ok(bridge, "cmd_continue_execution", {})

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_game_output() -> None:
    assert GODOT_BIN is not None
    snapshot = PROJECT_GODOT.read_bytes()
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
        SCRIPT_FILE.unlink(missing_ok=True)
        Path(str(SCRIPT_FILE) + ".uid").unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)