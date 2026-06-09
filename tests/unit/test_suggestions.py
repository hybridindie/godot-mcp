"""Unit tests for the suggestion engine (issue #109)."""

from __future__ import annotations

from mcp_server.suggestions import suggest


def test_exact_match_is_first() -> None:
    result = suggest("position", ["position", "global_position"])
    assert result[0] == "position"
    assert len(result) >= 1


def test_typo_returns_closest() -> None:
    result = suggest("positoin", ["position", "position_smoothing_enabled", "global_position"])
    assert result[0] == "position"


def test_empty_given_returns_empty() -> None:
    assert suggest("", ["a", "b"]) == []


def test_no_candidates_returns_empty() -> None:
    assert suggest("x", []) == []


def test_below_cutoff_returns_empty() -> None:
    assert suggest("zzzzzz", ["position"]) == []


def test_returns_up_to_n() -> None:
    result = suggest("pos", ["position", "position_smoothing_enabled", "global_position"], n=2)
    assert len(result) <= 2
