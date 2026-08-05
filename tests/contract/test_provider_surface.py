"""Contract test: no FastMCP private-internals reaches (issue #313).

The server must use FastMCP 4.0's public provider surface
(``mcp.local_provider.list_tools()`` / ``mcp.list_prompts()`` /
``mcp.list_resources()``) and ``ServerExtension`` rather than reading
``provider._components`` or calling the private ``mcp._list_tools()``. These
tests fail as soon as a private reach is reintroduced, since the source no
longer contains the offending tokens.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.helpers import list_all_tools

_SOURCE_FILES = [
    Path("mcp_server/safety.py"),
    Path("mcp_server/diagnostics.py"),
    Path("mcp_server/server.py"),
]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: Path) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def test_no_components_reach_in_source() -> None:
    """``provider._components`` / ``_local_provider._components`` must not appear."""
    offenders: list[str] = []
    for rel in _SOURCE_FILES:
        text = _read(rel)
        if "_components" in text:
            offenders.append(str(rel))
    assert not offenders, f"private _components reach still in: {offenders}"


def test_no_private_list_tools_in_source() -> None:
    """``mcp._list_tools()`` must not appear in server source."""
    offenders: list[str] = []
    for rel in _SOURCE_FILES:
        if "._list_tools(" in _read(rel):
            offenders.append(str(rel))
    assert not offenders, f"private _list_tools call still in: {offenders}"


def test_no_getattr_components_shim_in_source() -> None:
    """The defensive ``getattr(..., "_components", ...)`` shims must be gone."""
    for rel in _SOURCE_FILES:
        assert "_components" not in _read(rel), rel


@pytest.mark.asyncio
async def test_list_all_tools_includes_disabled() -> None:
    """The public helper returns the full set, not just the enabled subset."""
    mcp = create_server(ServerConfig())
    all_tools = await list_all_tools(mcp)
    async with Client(mcp, mode="legacy") as client:
        enabled = await client.list_tools()
    enabled_names = {t.name for t in enabled}
    all_names = {t.name for t in all_tools}
    assert enabled_names <= all_names
    assert len(all_tools) > len(enabled), (len(all_tools), len(enabled))


@pytest.mark.asyncio
async def test_local_provider_is_public_attribute() -> None:
    """``mcp.local_provider`` is a public attribute in FastMCP 4.0."""
    mcp = create_server(ServerConfig())
    assert mcp.local_provider is not None
    assert hasattr(mcp.local_provider, "list_tools")
    assert hasattr(mcp.local_provider, "list_prompts")
    assert hasattr(mcp.local_provider, "list_resources")


@pytest.mark.asyncio
async def test_public_list_prompts_and_resources_match_registry() -> None:
    """``mcp.list_prompts()`` / ``mcp.list_resources()`` are the public surface."""
    mcp = create_server(ServerConfig())
    prompts = await mcp.list_prompts()
    resources = await mcp.list_resources()
    assert prompts, "expected prompts registered"
    assert resources, "expected resources registered"
    assert all(hasattr(p, "name") for p in prompts)
    assert all(hasattr(r, "uri") for r in resources)
