"""Contract tests: TIMEOUT honesty for mutating commands (issue #644).

The addon drains commands serially on the editor main thread, so a command that
outlives the server timeout still runs later (its late reply is dropped). A
timeout on such a command must therefore say ``may_have_applied`` — otherwise an
agent retries and double-applies. Read-only commands carry no such flag.
"""

from __future__ import annotations

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import ResponseEnvelope
from tests.fakes import FakeAddonConnection, connector_for, immediate_sleep

pytestmark = pytest.mark.asyncio


async def _bridge(mutating: set[str]) -> Bridge:
    # A peer that never replies → every send times out.
    conn = FakeAddonConnection(responder=lambda _cmd: None)
    bridge = Bridge(
        BridgeConfig(request_timeout=5.0), connector=connector_for(conn), sleep=immediate_sleep
    )
    bridge.set_mutating_commands(frozenset(mutating))
    await bridge.connect()
    return bridge


async def test_timeout_on_mutating_command_flags_may_have_applied() -> None:
    bridge = await _bridge({"cmd_delete_node"})
    try:
        response = await bridge.send("cmd_delete_node", {"node_path": "X"})
    finally:
        await bridge.close()
    assert response.ok is False and response.error == "TIMEOUT"
    assert response.result == {"may_have_applied": True}
    assert "may still have applied" in (response.hint or "")


async def test_timeout_on_read_only_command_is_not_flagged() -> None:
    bridge = await _bridge({"cmd_delete_node"})
    try:
        response = await bridge.send("cmd_get_scene_tree", {})
    finally:
        await bridge.close()
    assert response.ok is False and response.error == "TIMEOUT"
    assert response.result is None  # no may_have_applied
    assert "may still have applied" not in (response.hint or "")


async def test_registry_classifies_the_mutating_commands() -> None:
    """The set the bridge uses is derived from the live registry (safety class)."""
    from mcp_server.config import ServerConfig
    from mcp_server.server import create_server
    from mcp_server.subcommand_policy import mutating_commands

    server = create_server(ServerConfig(), bridge=Bridge(ServerConfig().bridge))
    mutating = await mutating_commands(server)
    assert {"cmd_delete_node", "cmd_create_node", "cmd_set_node_property"} <= mutating
    assert {"cmd_get_scene_tree", "cmd_read_script", "cmd_get_active_scene"}.isdisjoint(mutating)


def test_timeout_flag_needs_a_mutating_command() -> None:
    # Guard: the enrichment is a no-op on a non-timeout or unknown command.
    bridge = Bridge(BridgeConfig())
    assert bridge._mutating_commands == frozenset()
    resp = ResponseEnvelope.failure("1", "VALIDATION_ERROR", "boom")
    assert bridge._flag_may_have_applied("cmd_delete_node", resp).result is None
