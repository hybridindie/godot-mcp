"""Contract tests for deferred command responses (issue #906).

A handler that cannot answer within the frame (a threaded navmesh bake) returns
the router's deferred marker; the router remembers the request ``id`` and the
handler later calls ``complete(id, body)``. ``MCPBridge`` sends the response
when the router's completion signal fires — same ``id``, same envelope shape,
one ``command_completed`` with the real exec_ms. Exactly one response per
``id``: a request that never completes is failed with ``TIMEOUT`` by an
addon-side timer set a little under the server's long-request timeout (#875),
and ``dispose()`` fails anything still pending.

The behaviour is pinned inside Godot by ``godot/tests/deferred_response_smoke.gd``;
the source checks pin the timeout budget against the server's default.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_server.config import DEFAULT_LONG_REQUEST_TIMEOUT, LONG_REQUEST_TIMEOUT_ENV
from tests.integration._godot import GODOT_BIN, run_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_DIR = REPO_ROOT / "godot" / "addons" / "godot_mcp"
ROUTER_GD = ADDON_DIR / "command_router.gd"
BRIDGE_GD = ADDON_DIR / "mcp_bridge.gd"
SMOKE = "deferred_response_smoke.gd"


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_deferred_response_smoke() -> None:
    """The headless smoke drives defer → complete / timeout / dispose in Godot."""
    result = run_godot(["--script", f"res://tests/{SMOKE}"])
    output = result.stdout + result.stderr
    assert "DEFERRED_RESPONSE_TEST_OK" in output, (
        f"deferred response smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_router_owns_the_deferred_api() -> None:
    """The router exposes the marker, completion and its signal."""
    src = ROUTER_GD.read_text()
    for needle in (
        "const DEFERRED_KEY",
        "signal deferred_completed(",
        "func defer() -> Dictionary",
        "func complete(id: String, body: Dictionary) -> bool",
        "func has_pending(id: String) -> bool",
    ):
        assert needle in src, f"{ROUTER_GD.name} missing {needle!r}"


def test_addon_timeout_is_just_under_the_server_long_timeout() -> None:
    """The addon fails a deferred request before the server gives up on it."""
    src = ROUTER_GD.read_text()
    match = re.search(r"const DEFAULT_DEFERRED_TIMEOUT_SEC := ([0-9.]+)", src)
    assert match, "router must declare DEFAULT_DEFERRED_TIMEOUT_SEC"
    addon_timeout = float(match.group(1))
    assert DEFAULT_LONG_REQUEST_TIMEOUT - 15.0 <= addon_timeout < DEFAULT_LONG_REQUEST_TIMEOUT
    # An operator who raises the server's long timeout raises the addon's too.
    assert LONG_REQUEST_TIMEOUT_ENV in src


def test_bridge_sends_on_completion() -> None:
    """The bridge listens for completions instead of only replying inline."""
    src = BRIDGE_GD.read_text()
    assert "deferred_completed.connect(" in src
