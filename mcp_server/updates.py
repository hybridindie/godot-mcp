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

from pydantic import BaseModel

from mcp_server import __version__
from mcp_server.versions import is_newer

logger = logging.getLogger(__name__)

GITHUB_LATEST_URL = "https://api.github.com/repos/hybridindie/godot-mcp/releases/latest"
PYPI_JSON_URL = "https://pypi.org/pypi/godot-editor-mcp/json"

# Returns the latest published version tag, or None when it can't be determined.
Fetcher = Callable[[], Awaitable[str | None]]


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


async def fetch_latest_release(timeout: float = 5.0) -> str | None:
    """Query GitHub Releases (falling back to PyPI) for the latest version tag.

    Returns ``None`` (never raises) on any network/parse failure, so a check can't
    break a tool call.
    """
    try:
        import httpx2 as httpx
    except Exception:  # pragma: no cover - httpx2 is a core dependency
        logger.warning("httpx2 unavailable; cannot check for updates")
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.get(
                    GITHUB_LATEST_URL,
                    headers={"Accept": "application/vnd.github+json"},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    tag = (resp.json() or {}).get("tag_name")
                    if isinstance(tag, str) and tag:
                        return tag
            except Exception:
                logger.debug("github latest-release lookup failed", exc_info=True)
            try:
                resp = await client.get(PYPI_JSON_URL, follow_redirects=True)
                if resp.status_code == 200:
                    version = ((resp.json() or {}).get("info") or {}).get("version")
                    if isinstance(version, str) and version:
                        return version
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
        url: str = GITHUB_LATEST_URL,
    ) -> None:
        self._enabled = enabled
        self._fetch: Fetcher = fetcher or fetch_latest_release
        self._clock: Callable[[], float] = clock or time.monotonic
        self._ttl = ttl_seconds
        self._url = url
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

        latest: str | None = None
        error: str | None = None
        try:
            latest = await self._fetch()
        except Exception as exc:  # a broken check must never break a tool call
            error = f"update check failed: {exc}"
            logger.warning("update check failed", exc_info=True)

        status = UpdateStatus(
            enabled=True,
            current=__version__,
            latest=latest,
            update_available=bool(latest and is_newer(latest, __version__)),
            url=self._url if latest else None,
            checked_at=_utcnow_iso(),
            error=error,
            hint=None if latest else "Could not reach the release feed; try again later.",
        )
        self._cached = status
        self._cached_at = self._clock()
        return status
