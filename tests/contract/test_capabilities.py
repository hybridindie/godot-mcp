"""Contract tests for the experimental_capabilities snapshot (issue #231).

The capabilities snapshot must be derived from the live registry, not hardcoded,
so it cannot silently drift from the real toolset / prompt / resource catalog.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from mcp_server import __version__
from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.toolsets import TOOLSETS
from tests.fakes import FakeAddonConnection, connector_for, make_addon_responder

pytestmark = pytest.mark.asyncio


def _server() -> FastMCP:
    config = ServerConfig()
    conn = FakeAddonConnection(make_addon_responder())
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge)


async def test_capabilities_derived_from_live_registry() -> None:
    server = _server()
    caps = server.experimental_capabilities["godot_mcp"]

    # toolset_count = the gated toolsets plus the always-on `core` toolset.
    assert caps["toolset_count"] == len(TOOLSETS) + 1

    async with Client(server) as client:
        prompt_names = {p.name for p in await client.list_prompts()}
        resource_uris = {str(r.uri) for r in await client.list_resources()}
        template_uris = {t.uri_template for t in await client.list_resource_templates()}

    assert set(caps["prompts"]) == prompt_names
    assert set(caps["resources"]) == resource_uris | template_uris


async def test_capabilities_static_fields_preserved() -> None:
    caps = _server().experimental_capabilities["godot_mcp"]
    assert caps["version"]
    assert caps["min_godot"]
    assert set(caps["docs"]) == {"tutorial", "tool_contracts", "architecture"}


async def test_capabilities_version_matches_package() -> None:
    """The advertised capability version must be the package's CalVer.

    It was hardcoded and drifted to ``2026.06.01`` while the package moved on —
    consumers reading ``experimental.godot_mcp.version`` saw a stale server.
    """
    caps = _server().experimental_capabilities["godot_mcp"]
    assert caps["version"] == __version__


async def test_capability_docs_links_resolve() -> None:
    """Every repo doc URL advertised by the capability snapshot must exist."""
    caps = _server().experimental_capabilities["godot_mcp"]
    repo_root = Path(__file__).resolve().parents[2]
    for name, path in {
        "tutorial": "docs/tutorial.md",
        "tool_contracts": "docs/tool-contracts.md",
        "architecture": "docs/architecture.md",
    }.items():
        assert caps["docs"][name].endswith("/" + path), (
            f"{name} capability points at {caps['docs'][name]}, expected {path}"
        )
        assert (repo_root / path).is_file(), f"capability doc is missing: {path}"
