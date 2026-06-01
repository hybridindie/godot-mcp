"""Integration test: the addon command router behaves correctly (issue #3).

Runs the headless GDScript exerciser ``godot/tests/bridge_smoke.gd`` and asserts
it reports success — pinning the command dispatch + structured-error contract
against the real Godot runtime, with no networking.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_command_router_dispatch_and_errors() -> None:
    result = run_godot(["--script", "res://tests/bridge_smoke.gd"])
    output = result.stdout + result.stderr
    assert "BRIDGE_TEST_OK" in output, (
        f"router smoke test did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
