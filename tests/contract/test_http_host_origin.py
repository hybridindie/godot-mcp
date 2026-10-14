"""Contract tests for HTTP Host/Origin protection (issue #636).

A browser (or a DNS-rebinding attacker whose page resolves to 127.0.0.1) can
reach the token-less loopback HTTP transport. FastMCP ships a Host/Origin guard
but leaves it off by default; godot-mcp defaults it **on** ("auto" — validate
Host and browser Origin for a loopback-bound server) so a non-loopback ``Host``
or a foreign ``Origin`` is refused before any code-executing tool is reachable.

The guard is exercised through the real ``http_app()`` ASGI middleware chain with
an in-process ASGI client (no socket): the guard is outermost, so a blocked
request returns before the MCP session manager is needed.
"""

from __future__ import annotations

from typing import Any

import fastmcp
import httpx2
import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_CLIENT = ("127.0.0.1", 4242)  # the loopback bind the guard keys off


def _http_app(config: ServerConfig | None = None) -> Any:
    cfg = config or ServerConfig()
    bridge = Bridge(cfg.bridge, connector=connector_for(FakeAddonConnection()))
    return create_server(cfg, bridge=bridge).http_app()


async def _get(app: Any, headers: dict[str, str]) -> int:
    transport = httpx2.ASGITransport(app=app, client=_CLIENT)
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/", headers=headers)
        return response.status_code


async def test_non_loopback_host_rejected_by_default() -> None:
    status = await _get(_http_app(), {"Host": "evil.example"})
    assert status == 421, "a non-loopback Host header must be refused (DNS rebinding)"


async def test_loopback_host_accepted_by_default() -> None:
    # The guard passes it through; "/" has no route, so it 404s (i.e. not 421).
    status = await _get(_http_app(), {"Host": "127.0.0.1"})
    assert status != 421


async def test_foreign_origin_rejected_by_default() -> None:
    status = await _get(
        _http_app(), {"Host": "127.0.0.1", "Origin": "https://evil.example"}
    )
    assert status == 403, "a foreign browser Origin must be refused"


async def test_opt_out_disables_protection() -> None:
    config = ServerConfig(http_host_origin_protection=False)
    status = await _get(_http_app(config), {"Host": "evil.example"})
    assert status != 421, "the documented opt-out must restore the old behavior"


async def test_create_server_applies_the_setting_to_fastmcp() -> None:
    """``http_app()`` (and ``run(transport='http')`` without an explicit value)
    read ``fastmcp.settings``, so the config must be pushed there — not only
    passed to ``http_app()``. Restores the global so the assertion can't leak
    into another test."""
    prior = fastmcp.settings.http_host_origin_protection
    try:
        _http_app(ServerConfig())
        assert fastmcp.settings.http_host_origin_protection == "auto"
        _http_app(ServerConfig(http_host_origin_protection=False))
        value: bool | str = fastmcp.settings.http_host_origin_protection
        assert value is False
    finally:
        fastmcp.settings.http_host_origin_protection = prior
