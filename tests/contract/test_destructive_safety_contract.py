"""Contract: every destructive-tagged tool calls require_confirmation (issue #367).

The destructive-tool safety contract is defense-in-depth by convention, not
enforced: ``ApprovalMiddleware`` gates a call on the tool's ``safety_class``
meta, but the ``confirm: bool`` gate lives in each tool's body via
``require_confirmation`` (safety.py:203). A tool tagged ``destructive`` whose
body forgets the call would be approved by the middleware and proceed without
``confirm=True`` — silently breaking the contract from mcp-tools.md.

This test pins the invariant statically: for every registered
``destructive``-tagged tool, the handler's source must call
``require_confirmation``. A new destructive tool added without the call fails
this test before it can ship.
"""

from __future__ import annotations

import inspect
import textwrap

import pytest

from mcp_server.safety import SafetyClass, _iter_registered_tools
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


async def _destructive_tool_handlers() -> list[tuple[str, object]]:
    """Return (tool_name, tool_object) for every destructive-tagged registered tool.

    Yields the registered Tool object (not the raw fn) so callers can read
    ``parameters`` (the JSON schema) directly — a client's ``list_tools``
    only shows enabled toolsets, so a gated destructive tool would be absent
    and a schema test would pass vacuously (issue #367 review feedback).
    """
    from mcp_server.bridge import Bridge
    from mcp_server.config import ServerConfig
    from mcp_server.server import create_server

    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    mcp = create_server(ServerConfig(), bridge=bridge)
    out: list[tuple[str, object]] = []
    async for tool in _iter_registered_tools(mcp):
        sc = (tool.meta or {}).get("safety_class")
        if sc == SafetyClass.DESTRUCTIVE.value:
            out.append((tool.name, tool))
    return out


async def test_every_destructive_tool_calls_require_confirmation() -> None:
    """Every destructive-tagged tool's handler must CALL require_confirmation
    (not just mention it in a comment). A destructive tool without the confirm
    gate would be approved by the middleware and run without confirm=True —
    violating the contract. This catches a missing call at contract-test time,
    before it ships.
    """
    import ast

    handlers = await _destructive_tool_handlers()
    assert handlers, "expected at least one destructive tool to be registered"
    missing: list[str] = []
    for name, tool in handlers:
        fn = getattr(tool, "fn", tool)
        src = textwrap.dedent(inspect.getsource(fn))  # type: ignore[arg-type]
        tree = ast.parse(src)
        called = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "require_confirmation"
            for node in ast.walk(tree)
        )
        if not called:
            missing.append(name)
    assert not missing, (
        "destructive tools missing a require_confirmation CALL (issue #367): "
        + ", ".join(missing)
    )


async def test_every_destructive_tool_accepts_dry_run() -> None:
    """Every destructive-tagged tool must accept ``dry_run`` (mcp-tools.md:
    destructive tools accept dry_run AND require confirm). Pin the schema.

    Reads the schema from the registered tool directly (via the unfiltered
    local provider), not from a client's ``list_tools`` — a client sees only
    enabled toolsets, so a gated destructive tool would be absent and the test
    would pass vacuously (issue #367 review feedback).
    """
    handlers = await _destructive_tool_handlers()
    assert handlers
    missing: list[str] = []
    for name, tool in handlers:
        props = (getattr(tool, "parameters", {}) or {}).get("properties", {})
        if "dry_run" not in props:
            missing.append(name)
    assert not missing, (
        "destructive tools missing dry_run in their schema (issue #367): "
        + ", ".join(missing)
    )


async def test_every_destructive_tool_accepts_confirm() -> None:
    """Every destructive-tagged tool must accept ``confirm`` (mcp-tools.md:
    destructive tools require confirm=True). Pin the schema.

    Reads the schema from the registered tool directly (via the unfiltered
    local provider), not from a client's ``list_tools``.
    """
    handlers = await _destructive_tool_handlers()
    assert handlers
    missing: list[str] = []
    for name, tool in handlers:
        props = (getattr(tool, "parameters", {}) or {}).get("properties", {})
        if "confirm" not in props:
            missing.append(name)
    assert not missing, (
        "destructive tools missing confirm in their schema (issue #367): "
        + ", ".join(missing)
    )