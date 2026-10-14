"""Unit tests for the res:// containment types (issue #637)."""

from __future__ import annotations

import pytest

from mcp_server.paths import ensure_export_path, ensure_res_path, escapes_res_root


@pytest.mark.parametrize(
    "bad",
    [
        "scenes/main.tscn",  # no scheme
        "/etc/passwd",  # absolute filesystem path
        "res://../evil.gd",  # escapes the root
        "res://..",
        "res://a/../../b.gd",
        "res:///etc/x.gd",  # scheme + absolute
    ],
)
def test_ensure_res_path_rejects_non_contained(bad: str) -> None:
    with pytest.raises(ValueError):
        ensure_res_path(bad)


@pytest.mark.parametrize(
    "good",
    [
        "res://scenes/main.tscn",
        "res://a/b/../c.gd",  # uses '..' but stays inside
        "res://",  # project root (valid for a directory)
        "res://.godot/imported/x.png",
    ],
)
def test_ensure_res_path_accepts_contained(good: str) -> None:
    assert ensure_res_path(good) == good


def test_escapes_res_root_matches_route_predicate() -> None:
    assert escapes_res_root("res://../x") is True
    assert escapes_res_root("res://../") is True
    assert escapes_res_root("res:///abs") is True
    assert escapes_res_root("res://a/../b") is False
    assert escapes_res_root("res://scenes/main.tscn") is False


def test_ensure_export_path_allows_absolute_but_rejects_empty() -> None:
    assert ensure_export_path("/tmp/build/game.x86_64") == "/tmp/build/game.x86_64"
    assert ensure_export_path("build/game.x86_64") == "build/game.x86_64"
    with pytest.raises(ValueError):
        ensure_export_path("")
    with pytest.raises(ValueError):
        ensure_export_path("a\x00b")
