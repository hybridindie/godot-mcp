"""Contract: require_node_exists uses a cheap cmd_node_exists probe (issue #365).

Previously require_node_exists sent cmd_get_node_properties (fetching every
property) for every node-targeted mutation, doubling the bridge round-trip.
It now sends a lightweight cmd_node_exists that returns only {exists: bool}.
The precondition envelope (RESOURCE_NOT_FOUND for missing, TIMEOUT/other
propagated) is unchanged.
"""

from __future__ import annotations

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.safety import PreconditionError, require_node_exists
from tests.fakes import FakeAddonConnection, Responder, connector_for

pytestmark = pytest.mark.asyncio


async def _connected(responder: Responder) -> Bridge:
    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    return bridge


def _sent_commands(conn: FakeAddonConnection) -> list[str]:
    return [CommandEnvelope.model_validate_json(s).command for s in conn.sent]


async def test_uses_cmd_node_exists_not_get_node_properties() -> None:
    """require_node_exists must send the cheap cmd_node_exists probe, not the
    heavy cmd_get_node_properties (issue #365)."""
    seen: list[str] = []

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        seen.append(cmd.command)
        return ResponseEnvelope.success(cmd.id, {"exists": True})

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    await require_node_exists(bridge, "Player")
    await bridge.close()

    assert "cmd_node_exists" in seen, (
        "require_node_exists must send cmd_node_exists, not "
        "cmd_get_node_properties (issue #365). Sent: " + ", ".join(seen)
    )
    assert "cmd_get_node_properties" not in seen


async def test_present_returns_without_error() -> None:
    """A present node returns silently (no PreconditionError)."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"exists": True})

    bridge = await _connected(responder)
    await require_node_exists(bridge, "Player")  # must not raise
    await bridge.close()


async def test_missing_raises_resource_not_found() -> None:
    """A missing node raises PreconditionError with error=RESOURCE_NOT_FOUND
    and required=node_exists (envelope unchanged)."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "No node at 'X'.")

    bridge = await _connected(responder)
    with pytest.raises(PreconditionError) as exc:
        await require_node_exists(bridge, "X")
    assert exc.value.error == "RESOURCE_NOT_FOUND"
    assert exc.value.required == "node_exists"
    await bridge.close()


async def test_other_failures_propagate_unchanged() -> None:
    """A TIMEOUT (or other non-not-found failure) propagates with its own
    error/required — not mislabeled as node_exists."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(cmd.id, "TIMEOUT", "No response from Godot.")

    bridge = await _connected(responder)
    with pytest.raises(PreconditionError) as exc:
        await require_node_exists(bridge, "Player")
    assert exc.value.error == "TIMEOUT"
    assert exc.value.required != "node_exists"
    await bridge.close()