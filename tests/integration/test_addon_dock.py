"""Integration test: the MCP status dock behaves correctly (issue #2).

Runs the headless GDScript exerciser ``godot/tests/dock_smoke.gd`` and asserts it
reports success. This pins the dock's state API — connection status, project /
scene / selected-node display, and the 10-entry recent-command log — against the
real Godot runtime, not a Python mock.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_dock_state_and_command_log() -> None:
    result = run_godot(["--script", "res://tests/dock_smoke.gd"])
    output = result.stdout + result.stderr
    assert "DOCK_TEST_OK" in output, (
        f"dock smoke test did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
