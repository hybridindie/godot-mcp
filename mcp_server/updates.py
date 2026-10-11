"""Opt-in update check (issue #629).

Off by default — no silent phone-home. When ``GODOT_MCP_CHECK_UPDATES`` is set,
the server can query the latest published version (GitHub Releases, falling back
to PyPI) and tell the agent/user when the server itself is behind. The fetcher and
clock are injectable so tests are deterministic and offline.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import NamedTuple

from pydantic import BaseModel

from mcp_server import __version__
from mcp_server.versions import is_newer

logger = logging.getLogger(__name__)

GITHUB_LATEST_API = "https://api.github.com/repos/hybridindie/godot-mcp/releases/latest"
GITHUB_RELEASES_URL = "https://github.com/hybridindie/godot-mcp/releases/latest"
PYPI_JSON_URL = "https://pypi.org/pypi/godot-editor-mcp/json"
PYPI_PROJECT_URL = "https://pypi.org/project/godot-editor-mcp/"


class LatestRelease(NamedTuple):
    """The latest published version and the URL of the source that reported it."""

    version: str
    url: str


# Returns the latest release (version + source URL), or None when undetermined.
Fetcher = Callable[[], Awaitable[LatestRelease | None]]


class UpdateStatus(BaseModel):
    """The result of an update check — always a value, never a raised error."""

    enabled: bool
    current: str
    latest: str | None = None
    update_available: bool = False
    url: str | None = None
    checked_at: str | None = None
    error: str | None = None
    hint: str | None = None


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def fetch_latest_release(timeout: float = 5.0) -> LatestRelease | None:
    """Query GitHub Releases (falling back to PyPI) for the latest version tag.

    Returns the version *and* the URL of whichever source answered, or ``None``
    (never raises) on any network/parse failure, so a check can't break a tool call.
    """
    try:
        import httpx2 as httpx
    except Exception:  # pragma: no cover - httpx2 is a core dependency (FastMCP 4)
        logger.warning("httpx2 unavailable; cannot check for updates")
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.get(
                    GITHUB_LATEST_API,
                    headers={"Accept": "application/vnd.github+json"},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json() or {}
                    tag = data.get("tag_name")
                    if isinstance(tag, str) and tag:
                        html_url = data.get("html_url")
                        url = (
                            html_url
                            if isinstance(html_url, str) and html_url
                            else GITHUB_RELEASES_URL
                        )
                        return LatestRelease(tag, url)
            except Exception:
                logger.debug("github latest-release lookup failed", exc_info=True)
            try:
                resp = await client.get(PYPI_JSON_URL, follow_redirects=True)
                if resp.status_code == 200:
                    version = ((resp.json() or {}).get("info") or {}).get("version")
                    if isinstance(version, str) and version:
                        return LatestRelease(version, PYPI_PROJECT_URL)
            except Exception:
                logger.debug("pypi version lookup failed", exc_info=True)
    except Exception:
        logger.debug("update http client failed", exc_info=True)
    return None


class UpdateChecker:
    """Checks for a newer release, caching the result for a TTL.

    ``enabled`` gates the network entirely: disabled ⇒ :meth:`check` returns a
    structured "disabled" status without any request. ``fetcher``/``clock`` are
    injectable for deterministic tests.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        fetcher: Fetcher | None = None,
        clock: Callable[[], float] | None = None,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._enabled = enabled
        self._fetch: Fetcher = fetcher or fetch_latest_release
        self._clock: Callable[[], float] = clock or time.monotonic
        self._ttl = ttl_seconds
        self._cached: UpdateStatus | None = None
        self._cached_at: float = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def cached(self) -> UpdateStatus | None:
        """The last result while it's within the TTL, else ``None``."""
        if self._cached is None:
            return None
        if self._clock() - self._cached_at > self._ttl:
            return None
        return self._cached

    async def check(self, *, force: bool = False) -> UpdateStatus:
        """Return the current update status (cached unless ``force``)."""
        if not self._enabled:
            return UpdateStatus(
                enabled=False,
                current=__version__,
                hint="Update checks are disabled. Set GODOT_MCP_CHECK_UPDATES=1 to enable them.",
            )
        if not force:
            fresh = self.cached()
            if fresh is not None:
                return fresh

        release: LatestRelease | None = None
        error: str | None = None
        try:
            release = await self._fetch()
        except Exception as exc:  # a broken check must never break a tool call
            error = f"update check failed: {exc}"
            logger.warning("update check failed", exc_info=True)

        status = UpdateStatus(
            enabled=True,
            current=__version__,
            latest=release.version if release else None,
            update_available=bool(release and is_newer(release.version, __version__)),
            # The URL reflects whichever feed actually answered (GitHub or PyPI).
            url=release.url if release else None,
            checked_at=_utcnow_iso(),
            error=error,
            hint=None if release else "Could not reach the release feed; try again later.",
        )
        self._cached = status
        self._cached_at = self._clock()
        return status
