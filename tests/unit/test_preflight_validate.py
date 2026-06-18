"""Unit tests for pre-flight validation (issues #176, #166).

Pre-flight is now **pure-string checks only**: node/parent existence is enforced
by ``require_*`` preconditions in the tool layer (``mcp_server/safety.py``), not
round-tripped here. Removing that round-trip — and the module-level cache that
backed it — is #166. These pin the surviving script-path rule and assert
preflight neither calls the bridge for existence nor keeps global state.
"""

from __future__ import annotations

import asyncio

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.tools._route import _preflight_validate, _validate_script_path
from tests.fakes import FakeAddonConnection, Responder, connector_for, ping_responder


def _counting_responder() -> tuple[Responder, list[str]]:
    """A responder that records every command it sees (for round-trip assertions)."""
    seen: list[str] = []

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        seen.append(cmd.command)
        return ping_responder(cmd)

    return responder, seen


async def _bridge(responder: Responder = ping_responder) -> Bridge:
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection(responder)))
    await bridge.connect()
    return bridge


def test_script_path_rejects_non_res_path() -> None:
    async def go() -> None:
        bridge = await _bridge()
        fail = await _validate_script_path(bridge, "cmd_write_script", {"script_path": "x.gd"})
        assert fail is not None and fail["required"] == "script_path"
        ok = await _validate_script_path(bridge, "cmd_write_script", {"script_path": "res://x.gd"})
        assert ok is None
        # read-only cmd_read_script is not a mutation → no validation
        skip = await _validate_script_path(bridge, "cmd_read_script", {"script_path": "x.gd"})
        assert skip is None
        await bridge.close()

    asyncio.run(go())


def test_preflight_rejects_bad_script_path() -> None:
    async def go() -> None:
        bridge = await _bridge()
        result = await _preflight_validate(bridge, "cmd_write_script", {"script_path": "bad.gd"})
        assert result["ok"] is False and result["required"] == "script_path"
        await bridge.close()

    asyncio.run(go())


def test_preflight_does_not_round_trip_node_existence() -> None:
    """#166: a mutation targeting a node must NOT round-trip cmd_get_node_properties
    in preflight — require_node_exists in the tool layer owns existence checks."""

    async def go() -> None:
        responder, seen = _counting_responder()
        bridge = await _bridge(responder)
        seen.clear()  # ignore the connect/ping handshake
        result = await _preflight_validate(bridge, "cmd_set_node_property", {"node_path": "Ghost"})
        assert result == {"ok": True}
        assert "cmd_get_node_properties" not in seen
        # cmd_create_node with a parent must likewise not probe the parent.
        result = await _preflight_validate(bridge, "cmd_create_node", {"parent_path": "Ghost"})
        assert result == {"ok": True}
        assert "cmd_get_node_properties" not in seen
        await bridge.close()

    asyncio.run(go())


def test_no_module_level_preflight_cache() -> None:
    """#166: the module-level mutable cache (an architecture violation) is removed."""
    import mcp_server.tools._route as route_mod

    assert not hasattr(route_mod, "_preflight_cache")
    assert not hasattr(route_mod, "_invalidate_preflight_cache")
    assert not hasattr(route_mod, "MUTATION_COMMANDS")
