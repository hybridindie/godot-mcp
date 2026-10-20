"""Unit tests for CalVer comparison + drift notices (issue #629)."""

from __future__ import annotations

from mcp_server.versions import is_newer, parse_calver, version_notice


def test_parse_calver() -> None:
    assert parse_calver("2026.10.10") == (2026, 10, 10)
    assert parse_calver("2026.10.10.1") == (2026, 10, 10, 1)
    # Legacy hyphen form is normalized, never silently dropped.
    assert parse_calver("2026.10.10-1") == (2026, 10, 10, 1)
    # Beta tags keep parsing to their date (no numeric revision).
    assert parse_calver("2026.08.26b1") == (2026, 8, 26)
    assert parse_calver("v2026.9.30") == (2026, 9, 30)
    assert parse_calver("nonsense") is None
    assert parse_calver("") is None


def test_is_newer() -> None:
    assert is_newer("2026.10.10", "2026.09.30") is True
    assert is_newer("2026.09.30", "2026.10.10") is False
    assert is_newer("2026.10.10", "2026.10.10") is False
    # A same-day patch is newer than its base, in both spellings.
    assert is_newer("2026.10.10.1", "2026.10.10") is True
    assert is_newer("2026.10.10-1", "2026.10.10") is True
    # An unparseable side never claims an update exists.
    assert is_newer("garbage", "2026.10.10") is False


def test_version_notice() -> None:
    assert version_notice("2026.10.10", "2026.10.10") is None
    assert version_notice("2026.10.10", None) is None
    newer_server = version_notice("2026.10.10", "2026.09.30")
    assert newer_server and "MISMATCH" in newer_server and "addon" in newer_server
    newer_addon = version_notice("2026.09.30", "2026.10.10")
    assert newer_addon and "server" in newer_addon
