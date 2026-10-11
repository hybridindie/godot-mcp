"""Unit tests for the opt-in update checker (issue #629).

Deterministic and offline: the fetcher and clock are injected.
"""

from __future__ import annotations

from mcp_server import __version__
from mcp_server.updates import LatestRelease, UpdateChecker

_NEWER = LatestRelease("9999.01.01", "https://example.invalid/9999")


async def test_disabled_makes_no_request() -> None:
    calls = {"n": 0}

    async def fetch() -> LatestRelease | None:
        calls["n"] += 1
        return _NEWER

    checker = UpdateChecker(enabled=False, fetcher=fetch)
    status = await checker.check()
    assert status.enabled is False
    assert status.update_available is False
    assert "GODOT_MCP_CHECK_UPDATES" in (status.hint or "")
    assert calls["n"] == 0  # no network when disabled


async def test_enabled_detects_a_newer_release() -> None:
    async def fetch() -> LatestRelease | None:
        return _NEWER

    status = await UpdateChecker(enabled=True, fetcher=fetch).check()
    assert status.enabled is True
    assert status.update_available is True
    assert status.latest == "9999.01.01"
    assert status.current == __version__
    assert status.url == "https://example.invalid/9999"


async def test_current_is_not_an_update() -> None:
    async def fetch() -> LatestRelease | None:
        return LatestRelease(__version__, "https://example.invalid/current")

    status = await UpdateChecker(enabled=True, fetcher=fetch).check()
    assert status.update_available is False


async def test_fetch_failure_is_reported_not_raised() -> None:
    async def fetch() -> LatestRelease | None:
        raise RuntimeError("network down")

    status = await UpdateChecker(enabled=True, fetcher=fetch).check()
    assert status.update_available is False
    assert status.error is not None and "network down" in status.error
    assert status.hint


async def test_result_is_cached_until_forced() -> None:
    calls = {"n": 0}

    async def fetch() -> LatestRelease | None:
        calls["n"] += 1
        return _NEWER

    checker = UpdateChecker(enabled=True, fetcher=fetch)
    await checker.check()
    await checker.check()  # served from cache
    assert calls["n"] == 1
    await checker.check(force=True)
    assert calls["n"] == 2


async def test_cache_expires_after_ttl() -> None:
    now = [0.0]
    calls = {"n": 0}

    async def fetch() -> LatestRelease | None:
        calls["n"] += 1
        return _NEWER

    checker = UpdateChecker(enabled=True, fetcher=fetch, clock=lambda: now[0], ttl_seconds=10.0)
    await checker.check()
    now[0] = 20.0  # past the TTL
    await checker.check()
    assert calls["n"] == 2
