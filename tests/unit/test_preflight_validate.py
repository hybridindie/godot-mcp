"""Unit tests for the split pre-flight validators (issue #176).

`_preflight_validate` was a 93-line linear wall; it's now an orchestrator over
per-rule validators. These pin each rule plus the orchestrator's caching and
short-circuit behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.tools._route import (
    _invalidate_preflight_cache,
    _preflight_cache,
    _preflight_validate,
    _validate_node_path,
    _validate_parent_path,
    _validate_script_path,
)
from tests.fakes import FakeAddonConnection, Responder, connector_for, ping_responder


def _node_responder(*, exists: bool) -> Responder:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_node_properties":
            if exists:
                return ResponseEnvelope.success(cmd.id, {"node_path": "X"})
            return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "no node")
        return ping_responder(cmd)
    return responder


async def _bridge(responder: Responder = ping_responder) -> Bridge:
    bridge = Bridge(BridgeConfig(), connector=connector_for(FakeAddonConnection(responder)))
    await bridge.connect()
    return bridge


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    # Clear before AND after: _preflight_cache is global, so leftover entries
    # would make other test modules order-dependent (cache hits skip validation).
    _invalidate_preflight_cache()
    yield
    _invalidate_preflight_cache()


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


def test_node_path_missing_node_fails_only_for_mutations() -> None:
    async def go() -> None:
        miss = await _bridge(_node_responder(exists=False))
        fail = await _validate_node_path(miss, "cmd_set_node_property", {"node_path": "Ghost"})
        assert fail is not None and fail["required"] == "node_path"
        # read-only command skips (addon returns its own envelope)
        skip = await _validate_node_path(miss, "cmd_get_node_properties", {"node_path": "Ghost"})
        assert skip is None
        await miss.close()
        present = await _bridge(_node_responder(exists=True))
        ok = await _validate_node_path(present, "cmd_set_node_property", {"node_path": "Player"})
        assert ok is None
        await present.close()
    asyncio.run(go())


def test_parent_path_missing_fails_dot_skips() -> None:
    async def go() -> None:
        miss = await _bridge(_node_responder(exists=False))
        fail = await _validate_parent_path(miss, "cmd_create_node", {"parent_path": "Ghost"})
        assert fail is not None and fail["required"] == "parent_path"
        ok = await _validate_parent_path(miss, "cmd_create_node", {"parent_path": "."})
        assert ok is None
        await miss.close()
    asyncio.run(go())


def test_preflight_caches_and_short_circuits() -> None:
    async def go() -> None:
        bridge = await _bridge(_node_responder(exists=False))
        params: dict[str, Any] = {"script_path": "bad.gd"}
        result = await _preflight_validate(bridge, "cmd_write_script", params)
        assert result["ok"] is False and result["required"] == "script_path"
        # failure cached
        assert _preflight_cache[f"cmd_write_script:{sorted(params.items())}"] is False
        # a clean command caches True
        ok = await _preflight_validate(bridge, "cmd_ping", {})
        assert ok == {"ok": True}
        assert _preflight_cache["cmd_ping:[]"] is True
        await bridge.close()
    asyncio.run(go())
