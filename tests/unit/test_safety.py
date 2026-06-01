"""Unit tests for the safety framework (issue #14)."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    RUNTIME,
    PreconditionError,
    SafetyClass,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_confirmation,
    require_node_exists,
)
from tests.fakes import FakeAddonConnection, Responder, connector_for

# asyncio_mode=auto handles the async tests; no module-wide mark (it would warn on
# the synchronous tests below).


def test_safety_meta_constants() -> None:
    assert READ_ONLY == {"safety_class": "read_only"}
    assert MUTATING == {"safety_class": "mutating"}
    assert DESTRUCTIVE == {"safety_class": "destructive"}
    assert RUNTIME == {"safety_class": "runtime"}
    assert SafetyClass.DESTRUCTIVE.value == "destructive"


async def _connected(responder: Responder) -> Bridge:
    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(BridgeConfig(), connector=connector_for(conn))
    await bridge.connect()
    return bridge


def test_require_bridge_connected_when_disconnected() -> None:
    bridge = Bridge(BridgeConfig())  # never connected
    with pytest.raises(PreconditionError) as exc:
        require_bridge_connected(bridge)
    assert exc.value.error == "BRIDGE_DISCONNECTED"
    assert exc.value.required == "bridge_connected"


async def test_require_active_scene_passes_when_open() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"is_open": True})

    bridge = await _connected(responder)
    await require_active_scene(bridge)  # must not raise
    await bridge.close()


async def test_require_active_scene_fails_when_closed() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"is_open": False})

    bridge = await _connected(responder)
    with pytest.raises(PreconditionError) as exc:
        await require_active_scene(bridge)
    assert exc.value.required == "active_scene"
    assert exc.value.error == "PRECONDITION_FAILED"
    await bridge.close()


async def test_require_node_exists_propagates_not_found() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "No node at 'X'.")

    bridge = await _connected(responder)
    with pytest.raises(PreconditionError) as exc:
        await require_node_exists(bridge, "X")
    assert exc.value.error == "RESOURCE_NOT_FOUND"
    await bridge.close()


async def test_require_node_exists_passes_when_present() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.success(cmd.id, {"node_path": "Player", "type": "Node2D"})

    bridge = await _connected(responder)
    await require_node_exists(bridge, "Player")  # must not raise
    await bridge.close()


async def test_require_node_exists_does_not_mislabel_other_failures() -> None:
    # A TIMEOUT must not be reported as a "node_exists" problem.
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope:
        return ResponseEnvelope.failure(cmd.id, "TIMEOUT", "No response from Godot.")

    bridge = await _connected(responder)
    with pytest.raises(PreconditionError) as exc:
        await require_node_exists(bridge, "Player")
    assert exc.value.error == "TIMEOUT"
    assert exc.value.required != "node_exists"
    await bridge.close()


def test_require_confirmation() -> None:
    require_confirmation(True, "delete_node")  # must not raise
    with pytest.raises(PreconditionError) as exc:
        require_confirmation(False, "delete_node")
    assert exc.value.required == "confirm"


async def test_enforce_preconditions_converts_to_tool_error() -> None:
    @enforce_preconditions
    async def boom() -> None:
        raise PreconditionError("Open a scene first.", required="active_scene")

    with pytest.raises(ToolError) as exc:
        await boom()
    message = str(exc.value)
    assert "PRECONDITION_FAILED" in message
    assert "active_scene" in message


async def test_enforce_preconditions_passes_through_success() -> None:
    @enforce_preconditions
    async def ok() -> str:
        return "done"

    assert await ok() == "done"
