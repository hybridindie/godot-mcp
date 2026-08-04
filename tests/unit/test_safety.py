"""Unit tests for the safety framework (issue #14)."""

from __future__ import annotations

from typing import Any

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


async def _collect(agen: Any) -> list[Any]:
    out: list[Any] = []
    async for item in agen:
        out.append(item)
    return out


def test_safety_meta_constants() -> None:
    assert READ_ONLY == {"safety_class": "read_only"}
    assert MUTATING == {"safety_class": "mutating"}
    assert DESTRUCTIVE == {"safety_class": "destructive"}
    assert RUNTIME == {"safety_class": "runtime"}
    assert SafetyClass.DESTRUCTIVE.value == "destructive"


def test_annotations_for_safety_class_mapping() -> None:
    from mcp_server.safety import annotations_for_safety_class

    ro = annotations_for_safety_class("read_only")
    assert ro is not None and ro.read_only_hint is True and ro.idempotent_hint is True

    mut = annotations_for_safety_class("mutating")
    assert mut is not None and mut.read_only_hint is False and mut.destructive_hint is False

    dest = annotations_for_safety_class("destructive")
    assert dest is not None and dest.read_only_hint is False and dest.destructive_hint is True

    run = annotations_for_safety_class("runtime")
    assert run is not None and run.read_only_hint is False and run.destructive_hint is False

    assert annotations_for_safety_class("unclassified") is None
    assert annotations_for_safety_class("bogus") is None


def test_apply_safety_annotations_respects_explicit_override() -> None:
    import asyncio

    from fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    from mcp_server.safety import READ_ONLY, apply_safety_annotations

    mcp = FastMCP("t")

    @mcp.tool(meta=READ_ONLY)
    async def derived() -> str:
        """doc"""
        return "x"

    @mcp.tool(meta=READ_ONLY, annotations=ToolAnnotations(title="Custom", read_only_hint=False))
    async def overridden() -> str:
        """doc"""
        return "x"

    apply_safety_annotations(mcp)

    # Read back via the public provider surface the production code uses.
    from mcp_server.safety import _iter_registered_tools

    by_name = {t.name: t for t in asyncio.run(_collect(_iter_registered_tools(mcp)))}
    assert by_name["derived"].annotations is not None
    assert by_name["derived"].annotations.read_only_hint is True
    # An explicit annotation set at registration is preserved, not overwritten.
    assert by_name["overridden"].annotations.title == "Custom"
    assert by_name["overridden"].annotations.read_only_hint is False


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
    # The hint must name the recovery path so an agent (no human) can act (#304).
    hint = exc.value.args[0]
    assert "create_scene" in hint and "open_scene" in hint and "list_scenes" in hint
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
    require_confirmation(True, "godot_scene_edit_delete_node")  # must not raise
    with pytest.raises(PreconditionError) as exc:
        require_confirmation(False, "godot_scene_edit_delete_node")
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
