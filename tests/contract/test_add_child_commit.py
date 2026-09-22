"""Contract tests for the add-child UndoRedo dedup (issue #528).

#522 moved the shared ``commit_add_child`` (+ ``commit_add_child_with_persistence``)
into ``mcp_helpers.gd``, but three sites still hand-roll the same
``create_action / add_do_method(add_child) / set_owner / add_do_reference /
add_undo_method(remove_child) / commit_action`` block: ``mutation._cmd_create_node``,
``composite._cmd_compose_node``, and ``composite._cmd_batch_create_nodes`` (the
composite legitimately needs an N-child variant). The persistence-verdict
stamping loop is also copy-pasted between ``batch.gd`` and ``composite.gd``.

Target contract (one implementation per pattern, in ``mcp_helpers.gd``):
1. Every single-child create routes through ``commit_add_child_with_persistence``.
2. The composite N-child case has one helper (``commit_add_children``).
3. Verdict stamping has one implementation (``persistence_entries``) used by
   batch + composite.
Source-scanned per the established pattern; live behavior is pinned by the
existing persistence e2e + composite contract suites.
"""

from __future__ import annotations

from pathlib import Path

ADDON_DIR = Path(__file__).resolve().parents[2] / "godot" / "addons" / "godot_mcp"
HELPERS_GD = ADDON_DIR / "mcp_helpers.gd"
MUTATION_GD = ADDON_DIR / "handlers" / "mutation.gd"
COMPOSITE_GD = ADDON_DIR / "handlers" / "composite.gd"
BATCH_GD = ADDON_DIR / "handlers" / "batch.gd"


def _fn(source: str, func: str) -> str:
    return source[source.index(f"func {func}") :].split("\nfunc ", 1)[0]


def test_helpers_host_the_add_child_commits() -> None:
    """mcp_helpers.gd owns both the single-child and N-child add commits."""
    src = HELPERS_GD.read_text()
    assert "func commit_add_child(" in src
    assert "func commit_add_child_with_persistence(" in src
    # The new composite variant (#528): N children in ONE undo action.
    assert "func commit_add_children(" in src, (
        "mcp_helpers.gd must host the N-child composite commit (#528)"
    )
    # The N-child helper registers every child as its own undo step (each
    # add_child + set_owner + add_undo remove_child inside one action).
    n_child = _fn(src, "commit_add_children")
    assert "add_do_method" in n_child and "add_undo_method" in n_child


def test_helpers_host_the_persistence_entries_helper() -> None:
    """One verdict-stamping implementation for per-node persistence entries."""
    src = HELPERS_GD.read_text()
    assert "func persistence_entries(" in src, (
        "mcp_helpers.gd must host the single-sourced _persistence_entries (#528)"
    )
    entries_fn = _fn(src, "persistence_entries")
    # It stamps the same shape the handlers do today: persisted/reason/hint.
    assert "persisted" in entries_fn and "reason" in entries_fn and "hint" in entries_fn


def test_create_node_uses_the_shared_commit() -> None:
    """mutation._cmd_create_node no longer hand-rolls the undo sequence."""
    fn = _fn(MUTATION_GD.read_text(), "_cmd_create_node")
    assert "commit_add_child_with_persistence" in fn, (
        "_cmd_create_node must route through the shared helpers commit (#528)"
    )
    assert "create_action" not in fn, "the inline undo block must be gone"
    assert 'add_do_method(parent, "add_child"' not in fn
    assert "add_undo_method(parent, \"remove_child\"" not in fn


def test_compose_node_uses_the_shared_commit() -> None:
    """composite._cmd_compose_node no longer hand-rolls the undo sequence."""
    fn = _fn(COMPOSITE_GD.read_text(), "_cmd_compose_node")
    assert "commit_add_children" in fn, (
        "_cmd_compose_node must route through the shared N-child commit (#528)"
    )
    assert "create_action" not in fn
    assert 'add_do_method(parent, "add_child"' not in fn


def test_batch_create_uses_the_shared_commit() -> None:
    """composite._cmd_batch_create_nodes no longer hand-rolls the undo loop."""
    fn = _fn(COMPOSITE_GD.read_text(), "_cmd_batch_create_nodes")
    assert "commit_add_children" in fn, (
        "_cmd_batch_create_nodes must route through the shared N-child commit (#528)"
    )
    assert "create_action" not in fn


def test_verdict_stamping_has_one_implementation() -> None:
    """batch.gd + composite.gd consume the shared persistence_entries helper;
    the copy-pasted {persisted, reason, hint} loops are gone."""
    entry_fns = [
        _fn(BATCH_GD.read_text(), "_cmd_batch_set_property"),
        _fn(COMPOSITE_GD.read_text(), "_cmd_apply_node_edits"),
    ]
    for i, fn in enumerate(entry_fns):
        assert "persistence_entries" in fn, (
            f"site {i} must stamp verdicts via the shared helper (#528)"
        )
        # The hand-stamped copy is gone: no direct verdict dict building.
        assert '{"node_path": node_path, "persisted": bool(verdict.get("ok", false))}' not in fn, (
            f"site {i} still hand-builds the verdict entry — use persistence_entries"
        )


def test_shared_commit_registers_the_n_child_action() -> None:
    """The composite variant opens exactly ONE action for N children and
    registers each child's undo removal — the manifest's one-action count
    stays intact through the refactor."""
    src = HELPERS_GD.read_text()
    fn = _fn(src, "commit_add_children")
    assert "create_action" in fn
    assert "commit_action" in fn
    assert fn.count("add_undo_method") >= 1