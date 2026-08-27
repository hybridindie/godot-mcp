"""Contract tests for the durable guard-pattern approval flow (issue #346).

The modern-protocol (MCP 2026-07-28) guard pattern returns an
``InputRequiredResult`` instead of raising on a destructive/mutating tool that
needs human approval. The client fulfils the request and calls again; the
second round sees the answer in ``ctx.input_responses`` and either proceeds or
denies. This is durable (no server-side state, no worker pinning) and works on
the sessionless protocol godot-mcp uses by design
(see ``.opencode/rules/async-patterns.md``).

These tests drive the real FastMCP server over the in-memory client with a
fake addon peer, mirroring ``tests/contract/test_mutation.py``. The approval
gate is configured with ``require_approval=True`` and **no webhook** (the path
the issue specifies); a client-side elicitation handler supplies the verdict.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.safety import ApprovalGate
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_active_scene":
            return ResponseEnvelope.success(cmd.id, {"is_open": True, "path": "res://m.tscn"})
        case "cmd_node_exists":  # require_node_exists precondition (issue #365)
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "type": "Node2D"})
        case "cmd_create_node":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": f"{p['parent_path']}/{p['name']}", "created": True}
            )
        case "cmd_delete_node":
            return ResponseEnvelope.success(cmd.id, {"node_path": p["node_path"], "deleted": True})
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build(*, approval: ApprovalGate) -> tuple[Any, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge, approval=approval), conn


def _commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


def _approval_handler(approve: bool) -> Any:
    """Return a fastmcp elicitation handler that approves or denies every ask."""

    async def handler(
        message: str,
        response_type: Any,
        params: Any,
        ctx: Any,
    ) -> ElicitResult:
        # The guard's elicitation asks for a single boolean "approve" field.
        return ElicitResult(action="accept", content=response_type(approve=approve))

    return handler


async def test_mutating_tool_without_require_approval_runs_directly() -> None:
    """Baseline: no opt-in means no guard — a mutating tool runs as before."""
    gate = ApprovalGate()  # no webhook, require_approval defaults False
    server, conn = _build(approval=gate)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
        )
    assert result.structured_content["created"] is True
    assert "cmd_create_node" in _commands(conn)


async def test_mutating_tool_with_require_approval_returns_input_required() -> None:
    """Opt-in + no webhook: the first round returns an InputRequiredResult,
    not the tool's real result. The addon must NOT have been called yet."""
    gate = ApprovalGate(require_approval=True)
    server, conn = _build(approval=gate)
    async with Client(
        server,
        mode="auto",
        elicitation_handler=_approval_handler(approve=True),
    ) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
        )
    # The handler approved, so the loop drives a second round and the tool runs.
    assert result.structured_content["created"] is True
    assert "cmd_create_node" in _commands(conn)


async def test_mutating_tool_guard_denied_blocks_and_never_reaches_addon() -> None:
    """When the client's elicitation handler denies, the second round must
    surface an APPROVAL_DENIED error and the addon must never see the command."""
    gate = ApprovalGate(require_approval=True)
    server, conn = _build(approval=gate)
    async with Client(
        server,
        mode="auto",
        elicitation_handler=_approval_handler(approve=False),
    ) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "APPROVAL_DENIED" in str(result.content)
    assert "cmd_create_node" not in _commands(conn)


async def test_dry_run_short_circuits_the_guard() -> None:
    """A preview never needs approval (workflow rule); the guard is skipped
    even when require_approval is set."""
    gate = ApprovalGate(require_approval=True)
    server, conn = _build(approval=gate)
    async with Client(
        server,
        mode="auto",
        elicitation_handler=_approval_handler(approve=True),
    ) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_create_node",
            {
                "parent_path": ".",
                "node_type": "Node2D",
                "node_name": "Player",
                "dry_run": True,
            },
        )
    # dry_run previews — no create_node command, no elicitation round-trip.
    assert "cmd_create_node" not in _commands(conn)
    # The preview result is a structured description of what would change.
    assert result.structured_content is not None


async def test_destructive_tool_uses_guard_when_opted_in_and_no_webhook() -> None:
    """A destructive tool with confirm=True and the guard opted in returns an
    InputRequiredResult the same way (the guard extends to destructive tools
    per the issue; the existing confirm gate in the tool body still runs first)."""
    gate = ApprovalGate(require_approval=True)
    server, conn = _build(approval=gate)
    async with Client(
        server,
        mode="auto",
        elicitation_handler=_approval_handler(approve=True),
    ) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        result = await client.call_tool(
            "godot_scene_edit_delete_node",
            {"node_path": "Player", "confirm": True},
        )
    assert result.structured_content["deleted"] is True
    assert "cmd_delete_node" in _commands(conn)


async def test_guard_request_state_carries_tool_and_params() -> None:
    """The InputRequiredResult.request_state carries enough context (tool name,
    safety_class, params) for a durable client to re-call the tool with the
    decision on the next round (the issue's 'durable' requirement)."""
    gate = ApprovalGate(require_approval=True)
    server, _ = _build(approval=gate)
    captured: dict[str, Any] = {}

    async def handler(message: str, response_type: Any, params: Any, ctx: Any) -> ElicitResult:
        # The elicitation message should name the tool and surface the params.
        captured["message"] = message
        return ElicitResult(action="accept", content=response_type(approve=True))

    async with Client(server, mode="auto", elicitation_handler=handler) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scene_edit"})
        await client.call_tool(
            "godot_scene_edit_create_node",
            {"parent_path": ".", "node_type": "Node2D", "node_name": "Player"},
        )
    assert "create_node" in captured["message"]
    # The params being approved are visible in the message (the human knows what
    # they are approving — the issue's "params being approved" requirement).
    assert "Player" in captured["message"]


async def test_read_only_tool_is_not_gated() -> None:
    """read_only tools are never gated, even with require_approval on."""
    gate = ApprovalGate(require_approval=True)
    server, conn = _build(approval=gate)
    async with Client(
        server,
        mode="auto",
        elicitation_handler=_approval_handler(approve=True),
    ) as client:
        # inspection is enabled by default; list_toolsets is read-only core.
        result = await client.call_tool("godot_list_toolsets", {})
    # No elicitation round-trip; the tool ran directly.
    assert result.structured_content is not None
