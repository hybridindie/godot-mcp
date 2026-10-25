"""Unit tests for the debug-workflow report builder (#796).

``build_report`` is pure, so the diagnostics' failure paths can be pinned
without a bridge: a command that *failed* must not be reported as "no scene
open" or silently look healthy.
"""

from __future__ import annotations

from mcp_server.debug_workflow import build_report


def _report(**overrides: object) -> tuple[list[str], list[str]]:
    kwargs: dict[str, object] = {
        "bridge_connected": True,
        "tree_result": {"tree": {"name": "Root"}},
        "run_result": None,
        "run_skipped": None,
        "parse_errors": [],
        "parse_skipped": None,
    }
    kwargs.update(overrides)
    return build_report(**kwargs)  # type: ignore[arg-type]


def test_scene_tree_failure_names_the_cause_instead_of_no_scene() -> None:
    findings, suggestions = _report(
        tree_result=None, tree_error="TIMEOUT: cmd_get_scene_tree did not answer"
    )

    assert any("SCENE TREE UNAVAILABLE" in f and "TIMEOUT" in f for f in findings)
    assert not any(f.startswith("NO ACTIVE SCENE") for f in findings)
    assert any("godot_health_check" in s for s in suggestions)


def test_scene_tree_absent_without_an_error_keeps_the_open_scene_finding() -> None:
    findings, _ = _report(tree_result=None)

    assert any(f.startswith("NO ACTIVE SCENE") for f in findings)
    assert not any("UNAVAILABLE" in f for f in findings)


def test_bridge_info_failure_is_reported_even_when_connected() -> None:
    findings, suggestions = _report(
        bridge_error="cmd_get_project_info failed: INTERNAL_ERROR: handler crashed"
    )

    assert any("BRIDGE INFO UNAVAILABLE" in f and "INTERNAL_ERROR" in f for f in findings)
    assert not any(f.startswith("BRIDGE DISCONNECTED") for f in findings)
    assert any("godot_health_check" in s for s in suggestions)
