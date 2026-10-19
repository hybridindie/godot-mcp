"""Behavioral contract tests for the router refactor (issue #522).

The router grew to ~800 lines of boilerplate: 31 preloads, 30 member vars, 30
``X.new(self) + register()`` pairs in ``_init()``, and a 30-line ``dispose()``
clearing each member by hand — four triplicated edits per new domain. Handlers
simultaneously reach into ~20 router *private* methods (``_resolve``,
``_property_type``, ``_persistent_target``, file I/O, persistence truth, ...),
so the router became a helpers grab-bag rather than pure dispatch, and the
handler↔router back-references form the RefCounted cycle ``dispose()`` exists
to break.

Target contract:
1. **Data-driven registration** — a single const table of
   ``[preload, ...]`` entries wired in one loop; ``dispose()`` is trivial
   (``_handlers.clear()`` + nulling the few real references), and adding a new
   domain handler is one table entry, not four edits.
2. **One helpers module** (``mcp_helpers.gd``) owns the shared logic — file
   I/O, node resolution, property-type cache, persistence truth, instantiation
   validation, batch-threshold decision — and handlers consume it directly.
3. The router stays dispatch + envelope builders + router-owned commands
   (ping/undo/run_commands/project-info/handshake).

This is the behavioral half: ``helpers_smoke.gd`` instantiates the router and
pins registration, table/disk coverage, helpers, threshold, and dispose at
runtime. The source-inspected architecture guards (where the logic
lives) are in ``tests/unit/test_router_architecture.py``.
"""

from __future__ import annotations

import pytest

from tests.integration._godot import GODOT_BIN, run_godot


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_helpers_smoke_pins_the_behavior() -> None:
    """The headless smoke exercises the helpers module + the data-driven router."""
    result = run_godot(["--script", "res://tests/helpers_smoke.gd"])
    output = result.stdout + result.stderr
    assert "HELPERS_TEST_OK" in output, (
        f"helpers smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output
