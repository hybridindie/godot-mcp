"""Contract tests for the threaded, deferred navmesh bake (issue #906).

``cmd_bake_navigation_mesh`` used to bake synchronously inside an UndoRedo
do-method, freezing the editor (and the readiness heartbeat) for the whole
bake. It now starts the bake with ``on_thread=true``, returns the router's
deferred marker, and completes the request when the region's ``bake_finished``
fires: exactly one response, heartbeats keep flowing, a second bake of the same
region is refused with ``EDITOR_BUSY``, and undo restores the previous mesh.

The behaviour is pinned inside Godot by ``godot/tests/deferred_bake_smoke.gd``;
the router's deferred bookkeeping (one completion, the TIMEOUT path) is pinned
by ``deferred_response_smoke.gd`` (``test_deferred_response.py``). The source
checks keep the handler on the deferred, threaded path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

REPO_ROOT = Path(__file__).resolve().parents[2]
NAVIGATION_GD = REPO_ROOT / "godot" / "addons" / "godot_mcp" / "handlers" / "navigation.gd"
SMOKE = "deferred_bake_smoke.gd"


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_deferred_bake_smoke() -> None:
    """The headless smoke bakes a NavigationRegion3D on a thread through the router."""
    result = run_godot(["--script", f"res://tests/{SMOKE}"])
    output = result.stdout + result.stderr
    assert "DEFERRED_BAKE_TEST_OK" in output, (
        f"deferred bake smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_bake_runs_on_a_thread() -> None:
    """No synchronous bake is left: both region types bake with on_thread=true."""
    src = NAVIGATION_GD.read_text()
    assert not re.search(r"bake_navigation_(mesh|polygon)\b[^\n]*\bfalse\b", src), (
        "navigation.gd still bakes synchronously (on_thread=false)"
    )
    assert "bake_navigation_mesh(true)" in src
    assert "bake_navigation_polygon(true)" in src


def test_bake_answers_through_the_deferred_response() -> None:
    """The handler defers, completes on bake_finished, and refuses a concurrent bake."""
    src = NAVIGATION_GD.read_text()
    for needle in ("_router.defer()", "_router.is_deferred(", "_router.complete(", "bake_finished"):
        assert needle in src, f"navigation.gd missing {needle!r}"
    assert '"EDITOR_BUSY"' in src, "a second bake on a busy region must be refused"


def test_bake_completion_respects_concurrent_edits() -> None:
    """Round-1 review: a mid-bake edit is not clobbered, shared meshes are locked."""
    src = NAVIGATION_GD.read_text()
    # Completion checks the property still holds the working copy.
    assert "region.get(prop) != working" in src
    # The lock covers the source resource, not only the region.
    assert '"resources": [source_id, working.get_instance_id()]' in src
    # A request answered without bake_finished releases its lock.
    assert "deferred_completed.connect(_on_request_answered)" in src
