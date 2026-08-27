"""Contract: middlewares fail closed on tool-lookup errors (issue #369).

The toolset and approval middlewares both had ``except Exception: return
True`` / ``return await call_next(context)`` branches that silently allowed
gated calls when ``get_tool`` raised an unexpected error. For the approval
gate that is fail-*open* on a destructive tool — the opposite of fail-safe.
``safety.py:219`` (``parse_approval_response``) fails safe to *denied* on a
malformed webhook; the middlewares must match.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from mcp_server.approval_middleware import ApprovalMiddleware
from mcp_server.safety import ApprovalGate
from mcp_server.toolset_middleware import ToolsetMiddleware

pytestmark = pytest.mark.asyncio


class _FakeFastMCP:
    """FastMCP stand-in whose get_tool raises a non-ToolError exception."""

    async def get_tool(self, _name: str, _version: str | None = None) -> Any:
        raise RuntimeError("simulated FastMCP internal lookup failure")


class _FakeCtx:
    fastmcp = _FakeFastMCP()


class _FakeMessage:
    name = "godot_scene_edit_delete_node"
    arguments: dict[str, Any] = {}


class _FakeContext:
    def __init__(self) -> None:
        self.fastmcp_context = _FakeCtx()
        self.message = _FakeMessage()


# ---------------------------------------------------------------------------
# Approval middleware: fail closed (deny) on lookup error
# ---------------------------------------------------------------------------


async def test_approval_gate_denies_on_lookup_error() -> None:
    """When get_tool raises a non-ToolError exception, a destructive tool
    call must be DENIED, not passed through the approval gate. Fail-safe
    matches parse_approval_response (deny on unparseable)."""
    gate = ApprovalGate()  # no webhook → middleware evaluates safety_class via lookup
    mw = ApprovalMiddleware(gate)
    ctx = _FakeContext()

    async def _call_next(_ctx: Any) -> Any:
        return "RAN"  # sentinel: if reached, the gate failed open

    with pytest.raises(ToolError) as exc:
        await mw.on_call_tool(ctx, _call_next)  # type: ignore[arg-type]
    assert "fail-closed" in str(exc.value).lower()


async def test_approval_gate_toolerror_still_passes_through() -> None:
    """A genuine ToolError (FastMCP 'no such tool') is still passed through —
    that is FastMCP's own not-found signal, not a lookup failure, and the
    server's own error handling surfaces it. Only *unexpected* exceptions
    fail closed."""

    class _ToolErrorFastMCP:
        async def get_tool(self, _name: str, _version: str | None = None) -> Any:
            raise ToolError("no such tool")

    class _Ctx:
        fastmcp = _ToolErrorFastMCP()

        class _Message:
            name = "godot_scene_edit_delete_node"
            arguments: dict[str, Any] = {}

    class _C:
        def __init__(self) -> None:
            self.fastmcp_context = _Ctx()
            self.message = _Ctx._Message()

    gate = ApprovalGate()
    mw = ApprovalMiddleware(gate)
    ctx = _C()

    async def _call_next(_ctx: Any) -> Any:
        return "PASSED"

    result = await mw.on_call_tool(ctx, _call_next)  # type: ignore[arg-type]
    assert result == "PASSED", (
        "approval middleware should pass through on a ToolError (no-such-tool), "
        "not deny (issue #369)."
    )


# ---------------------------------------------------------------------------
# Toolset middleware: fail open (allow) so core recovery stays reachable
# ---------------------------------------------------------------------------


async def test_toolset_gate_allows_on_lookup_error(caplog: pytest.LogCaptureFixture) -> None:
    """When get_tool raises a non-ToolError exception, a gated tool call is
    ALLOWED through the toolset gate (fail-open) — so the agent can still
    reach core recovery tools (godot_list_toolsets, godot_enable_toolset) when
    an internal lookup error occurs. The approval gate is the
    security-critical one and fails closed; the toolset gate is surface
    management. The failure is logged at ERROR so it is visible, not silent."""
    mw = ToolsetMiddleware()
    ctx = _FakeContext()

    async def _call_next(_ctx: Any) -> Any:
        return "RAN"

    with caplog.at_level("ERROR", logger="mcp_server.toolset_middleware"):
        result = await mw.on_call_tool(ctx, _call_next)  # type: ignore[arg-type]
    # Fail-open: the tool runs.
    assert result == "RAN"
    # But the failure is logged at ERROR (not silently swallowed).
    assert any(
        "unexpected error looking up tool" in r.message and r.levelno == 40
        for r in caplog.records
    ), "toolset gate must log lookup errors at ERROR even when failing open"


async def test_toolset_gate_toolerror_still_passes_through() -> None:
    """A genuine ToolError (no such tool) still passes through to FastMCP's
    own error handling."""

    class _ToolErrorFastMCP:
        async def get_tool(self, _name: str, _version: str | None = None) -> Any:
            raise ToolError("no such tool")

    class _Ctx:
        fastmcp = _ToolErrorFastMCP()

        class _Message:
            name = "godot_scene_edit_create_node"
            arguments: dict[str, Any] = {}

    class _C:
        def __init__(self) -> None:
            self.fastmcp_context = _Ctx()
            self.message = _Ctx._Message()

    mw = ToolsetMiddleware()
    ctx = _C()

    async def _call_next(_ctx: Any) -> Any:
        return "PASSED"

    result = await mw.on_call_tool(ctx, _call_next)  # type: ignore[arg-type]
    assert result == "PASSED"


# ---------------------------------------------------------------------------
# Toolset middleware: read-only tools are never blocked by lookup errors
# ---------------------------------------------------------------------------


async def test_toolset_gate_readonly_core_tool_passes_on_lookup_error() -> None:
    """A core-tagged tool (always visible) is not subject to the lookup, so a
    lookup error never blocks it — core stays reachable for recovery."""
    mw = ToolsetMiddleware()

    class _Msg:
        name = "godot_list_toolsets"  # core tag
        arguments: dict[str, Any] = {}

    class _C:
        def __init__(self) -> None:
            self.fastmcp_context = _FakeCtx()
            self.message = _Msg()

    async def _call_next(_ctx: Any) -> Any:
        return "PASSED"

    result = await mw.on_call_tool(_C(), _call_next)  # type: ignore[arg-type]
    assert result == "PASSED"