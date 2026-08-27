"""Contract tests: toolset gating is server-global (issue #364).

godot-mcp is a single-user, locally-run MCP server — one client per Godot
instance. Per-session isolation was dead code on the sessionless
``2026-07-28`` protocol real clients use (fresh ``session_id`` per call), and
``Middleware.on_initialize`` violated ``.opencode/rules/async-patterns.md``.

The enabled set is now a single server-global set:
  - ``enable_toolset`` / ``disable_toolset`` mutate it directly.
  - All clients (sessionless or legacy) see the same surface.
  - The default surface (core + inspection) is enforced from the first call,
    without any server-initiated hook.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.toolset_middleware import ToolsetMiddleware
from tests.fakes import FakeAddonConnection, connector_for


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


# ---------------------------------------------------------------------------
# 1. No on_initialize hook (the async-patterns rule)
# ---------------------------------------------------------------------------


def test_toolset_middleware_does_not_override_on_initialize() -> None:
    """``ToolsetMiddleware`` must not override ``Middleware.on_initialize``.

    ``.opencode/rules/async-patterns.md`` forbids ``Middleware.on_initialize``
    on the sessionless protocol. The enabled set is server-global, so no
    per-session seeding hook is needed.
    """
    from fastmcp.server.middleware import Middleware as _Base

    own = ToolsetMiddleware.__dict__.get("on_initialize", None)
    base = getattr(_Base, "on_initialize", None)
    assert own is None or own is base, (
        "ToolsetMiddleware overrides on_initialize, which violates the "
        "sessionless-protocol rule (.opencode/rules/async-patterns.md)."
    )


# ---------------------------------------------------------------------------
# 2. Server-global: state is shared across clients, works on sessionless
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_persists_across_clients_sessionless() -> None:
    """A toolset enabled in one client connection is visible to a later,
    independent client — the state is server-global, not per-session. This
    works on the default sessionless protocol (no ``mode="legacy"`` needed).
    """
    server, _ = _build()
    async with Client(server) as a:  # sessionless (default)
        before = {t.name for t in await a.list_tools()}
        assert "godot_scene_edit_create_node" not in before
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})

    # A fresh, independent client sees the state set by the first.
    async with Client(server) as b:
        after = {t.name for t in await b.list_tools()}
    assert "godot_scene_edit_create_node" in after


@pytest.mark.asyncio
async def test_disable_persists_across_clients_sessionless() -> None:
    """A toolset disabled in one connection stays disabled for the next."""
    server, _ = _build()
    async with Client(server) as a:
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await a.call_tool("godot_disable_toolset", {"category": "scene_edit"})

    async with Client(server) as b:
        names = {t.name for t in await b.list_tools()}
    assert "godot_scene_edit_create_node" not in names


@pytest.mark.asyncio
async def test_default_surface_enforced_on_sessionless_first_call() -> None:
    """The default surface (core + inspection) is enforced from the very
    first ``list_tools`` on the sessionless protocol — no ``on_initialize``
    hook needed to seed it.
    """
    server, _ = _build()
    async with Client(server) as client:  # sessionless, no mode="legacy"
        names = {t.name for t in await client.list_tools()}
    # Default tools are visible...
    assert "godot_health_check" in names
    assert "godot_inspection_get_scene_tree" in names
    # ...and gated tools are NOT, on the first call.
    assert "godot_scene_edit_create_node" not in names
    assert "godot_visual_shader_create" not in names


@pytest.mark.asyncio
async def test_enable_then_call_gated_tool_on_sessionless() -> None:
    """Enabling a toolset and then calling one of its tools works on the
    sessionless protocol — the enabled state persists across the two calls
    even though each gets a fresh ``session_id``.
    """
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": "root", "node_type": "Node", "node_name": "n"},
            raise_on_error=False,
        )
    # Not a "not enabled in this session" error — the tool ran.
    msg = str(result.content).lower()
    assert "not enabled" not in msg


# ---------------------------------------------------------------------------
# 3. Shared state across concurrent clients (no isolation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_is_shared_not_isolated_across_concurrent_clients() -> None:
    """Two concurrent clients share the enabled set — one enabling a toolset
    exposes it to the other. This is the intended behavior for a single-user
    local server (issue #364).
    """
    server, _ = _build()
    async with Client(server, mode="legacy") as a, Client(server, mode="legacy") as b:
        await a.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        names_b = {t.name for t in await b.list_tools()}
    # B sees the toolset A enabled — shared state, no isolation.
    assert "godot_scene_edit_create_node" in names_b