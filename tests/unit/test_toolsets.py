"""Unit tests for toolset gating logic (issue #26 extension: version gates)."""

from __future__ import annotations

import pytest

from mcp_server.toolsets import TOOLSET_MIN_GODOT, TOOLSETS, _parse_godot_version


@pytest.mark.parametrize(
    "version_str,expected",
    [
        ("4.4.1-stable", (4, 4)),
        ("4.4.0-stable", (4, 4)),
        ("4.3.2-stable", (4, 3)),
        ("4.10.0-dev", (4, 10)),
        ("3.5.1", (3, 5)),
        ("5.0.0-alpha1", (5, 0)),
    ],
)
def test_parse_godot_version_valid(version_str: str, expected: tuple[int, int]) -> None:
    assert _parse_godot_version(version_str) == expected


@pytest.mark.parametrize("version_str", ["", "not-a-version", "v4", "4"])
def test_parse_godot_version_returns_none_for_invalid(version_str: str) -> None:
    assert _parse_godot_version(version_str) is None


def test_toolset_min_godot_keys_are_valid_categories() -> None:
    """Every entry in TOOLSET_MIN_GODOT must correspond to a known toolset."""
    for category in TOOLSET_MIN_GODOT:
        assert category in TOOLSETS, f"Unknown toolset '{category}' in TOOLSET_MIN_GODOT"


def test_toolset_min_godot_tuple_ordering() -> None:
    """Version comparison via tuple < works as expected for Godot versions."""
    assert (4, 3) < (4, 4)
    assert (4, 4) < (4, 5)
    assert (3, 5) < (4, 4)
    assert (4, 4) == (4, 4)
    assert not ((4, 4) < (4, 4))
