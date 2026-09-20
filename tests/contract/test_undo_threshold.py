"""Contract tests for the shared UndoRedo 20-node threshold (issue #523).

#461 gave ``batch_set_property`` an honest ``undoable: false`` + hint when a
batch exceeds the 20-node UndoRedo threshold (perf cliff), but the threshold
lived in one file with the local const dead and the literal hardcoded twice —
while ``composite.gd``'s ``batch_create_nodes`` / ``apply_node_edits`` have
**no threshold at all**: a 500-node batch create opens one giant UndoRedo
action and reports nothing about undo coverage.

Fix contract: one shared const (``MCP_UNDO_THRESHOLD`` in the addon, declared
once), used by all three batch-apply paths; the composite tools return the
same ``undoable`` + ``hint`` honesty fields ``batch_set_property`` does, so a
consumer reads one shape. Source-scanned per the established pattern (the
addon is GDScript); the live behavioral check is ``godot/tests/threshold_smoke.gd``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._godot import GODOT_BIN, run_godot

ADDON_DIR = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
ROUTER_GD = ADDON_DIR / "command_router.gd"
BATCH_GD = ADDON_DIR / "handlers" / "batch.gd"
COMPOSITE_GD = ADDON_DIR / "handlers" / "composite.gd"

THRESHOLD = 20


def _fn(source: str, func: str) -> str:
    return source[source.index(f"func {func}") :].split("\nfunc ", 1)[0]


def test_threshold_is_a_single_shared_const() -> None:
    """One const + one decision site own the threshold; no literal 20 survives
    in the handlers."""
    router_src = ROUTER_GD.read_text()
    assert "const MCP_UNDO_THRESHOLD := 20" in router_src, (
        "command_router.gd must declare the shared UndoRedo threshold const"
    )
    assert "func _undoable_for_count" in router_src, (
        "command_router.gd must host the one decision site (_undoable_for_count)"
    )
    assert "func _undo_threshold_hint" in router_src, (
        "command_router.gd must host the single-sourced hint (_undo_threshold_hint)"
    )
    batch_src = BATCH_GD.read_text()
    composite_src = COMPOSITE_GD.read_text()
    batch_fn = _fn(batch_src, "_cmd_batch_set_property")
    assert "var undo_threshold := 20" not in batch_fn, (
        "batch.gd: dead local const — use the shared const"
    )
    assert "to_apply.size() > 20" not in batch_src, (
        "batch.gd: hardcoded threshold literal — use the shared const"
    )
    assert "20-node" not in batch_src, (
        "batch.gd: hint hardcodes the threshold — interpolate the const"
    )
    # All three call sites go through the shared decision, never re-derive it:
    for name, src in (("batch.gd", batch_src), ("composite.gd", composite_src)):
        assert "_undoable_for_count" in src, f"{name}: must use _undoable_for_count"
        assert "_undo_threshold_hint" in src, f"{name}: must use _undo_threshold_hint"


def test_composite_batch_creates_return_undoable_fields() -> None:
    """batch_create_nodes / apply_node_edits return the same honesty shape as
    batch_set_property (undoable + hint), threshold-aware via the shared
    decision site on the router."""
    composite_src = COMPOSITE_GD.read_text()
    for fn in ("_cmd_batch_create_nodes", "_cmd_apply_node_edits"):
        body = _fn(composite_src, fn)
        assert '"undoable"' in body, (
            f"{fn} must report the undoable honesty field (issue #523)"
        )
        assert "_undoable_for_count" in body, f"{fn} must be threshold-aware"
        assert "_undo_threshold_hint" in body, (
            f"{fn}: the non-undoable case must carry the recovery hint"
        )


def test_threshold_hint_interpolates_the_const() -> None:
    """The hint text is single-sourced on the router and names the threshold
    from the const — a future retune updates one place, hints included."""
    router_src = ROUTER_GD.read_text()
    hint_fn = _fn(router_src, "_undo_threshold_hint")
    # The wording contract lives in ONE place and interpolates the const:
    assert "exceeds" in hint_fn, "the #461 hint wording must live on the router"
    assert "%d-node UndoRedo threshold" in hint_fn
    assert "Undo will not revert" in hint_fn
    assert "MCP_UNDO_THRESHOLD" in hint_fn, (
        "the hint must interpolate the const, not a literal"
    )
    # No hardcoded "20-node" phrasing survives in any handler.
    for name, src in (
        ("batch.gd", BATCH_GD.read_text()),
        ("composite.gd", COMPOSITE_GD.read_text()),
    ):
        assert "20-node" not in src, f"{name}: hint hardcodes the threshold"


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_threshold_smoke_pins_the_boundary() -> None:
    """The headless smoke drives the threshold boundary (19/20/21 semantics)."""
    result = run_godot(["--script", "res://tests/threshold_smoke.gd"])
    output = result.stdout + result.stderr
    assert "THRESHOLD_TEST_OK" in output, (
        f"threshold smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}:\n{output}"
    assert "SCRIPT ERROR" not in output


def test_docs_name_the_shared_threshold() -> None:
    contracts = Path(__file__).resolve().parents[2] / "docs" / "tool-contracts.md"
    src = contracts.read_text()
    # The composite tools' contract rows carry the undoable field.
    assert "BatchCreateNodesResult { created[], count, saved, undoable, hint?" in src, (
        "docs/tool-contracts.md: composite batch create must document undoable+hint"
    )
    assert (
        "ApplyNodeEditsResult { edited[], skipped[], count, saved, undoable, "
        "hint?, persistence[] }" in src
    )