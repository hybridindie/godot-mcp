"""Unit: classify the connected Godot engine against the support surface (#588)."""

from __future__ import annotations

import pytest

from mcp_server.godot_support import (
    FLOOR,
    VALIDATED,
    VERIFIED_AGAINST,
    classify_godot_version,
)


def test_constants_match_the_repo_claims() -> None:
    assert FLOOR == (4, 4)
    assert VALIDATED == (4, 7)
    assert VERIFIED_AGAINST == "4.8-beta2"


def test_no_engine_is_disconnected_not_an_error() -> None:
    info = classify_godot_version(None)
    assert info.status == "disconnected"
    assert info.detected is None
    assert info.notice is None


@pytest.mark.parametrize(
    ("version", "status"),
    [
        ("4.7.2-stable (official)", "validated"),
        ("4.7.stable.official.5b4e0cb0f", "validated"),
        ("4.6.3-stable", "supported"),
        ("4.4.1-stable", "supported"),
        ("4.8.beta2.official.cafc17a19", "prerelease"),
        ("4.8-beta2", "prerelease"),
        ("4.8.rc1.official.abc", "prerelease"),
        ("4.8.stable.official.abc", "newer"),
        ("4.9.dev1", "prerelease"),
        ("4.3.stable", "below_floor"),
        ("3.6.3-stable", "below_floor"),
    ],
)
def test_status_matrix(version: str, status: str) -> None:
    assert classify_godot_version(version).status == status


def test_validated_engine_has_no_notice() -> None:
    info = classify_godot_version("4.7.2-stable (official)")
    assert info.notice is None


def test_beta_notice_names_the_verified_binary() -> None:
    info = classify_godot_version("4.8.beta2.official.cafc17a19")
    assert "prerelease" in (info.notice or "")
    assert VERIFIED_AGAINST in (info.notice or "")
    assert "4.7" in (info.notice or "")


def test_below_floor_notice_is_actionable() -> None:
    info = classify_godot_version("4.3.stable")
    assert "4.4" in (info.notice or "")
    assert "Upgrade" in (info.notice or "")


@pytest.mark.parametrize("version", ["", "nonsense", "godot"])
def test_malformed_string_is_unknown_not_a_crash(version: str) -> None:
    info = classify_godot_version(version)
    if version == "":
        assert info.status == "disconnected"
    else:
        assert info.status == "unknown"
        assert info.notice is not None


def test_beta10_does_not_parse_as_beta1() -> None:
    # The prerelease token regex is not anchored to a single digit.
    info = classify_godot_version("4.8.beta10.official.abc")
    assert info.status == "prerelease"
