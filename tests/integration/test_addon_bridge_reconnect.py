"""Integration test: the addon bridge's reconnect/backoff state machine (#276).

Runs the headless GDScript exerciser ``godot/tests/bridge_reconnect_smoke.gd`` and
asserts it reports success — pinning the WebSocket-client backoff doubling/cap and the
retry-countdown reconnect deterministically against the real Godot runtime, with no
networking (the live e2e covers an actual server round-trip).
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")


def test_addon_bridge_reconnect_backoff() -> None:
    result = run_godot(["--script", "res://tests/bridge_reconnect_smoke.gd"])
    output = result.stdout + result.stderr
    assert "BRIDGE_RECONNECT_TEST_OK" in output, (
        f"reconnect smoke test did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
