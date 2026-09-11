"""A reply the bridge can't parse as an envelope must not strand its request (#466).

When an addon handler dies on a GDScript error, the router answers ``{"id": ...}`` with
no ``ok``. Dropping that as unparseable left the caller waiting out the full request
timeout for a reply that had already arrived; it now resolves as ``INTERNAL_ERROR``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ErrorCode
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


class _RawReplyConnection(FakeAddonConnection):
    """Answers every command with a raw payload built from its id."""

    def __init__(self, reply: str) -> None:
        super().__init__()
        self._reply = reply

    async def send(self, message: str) -> None:
        self.sent.append(message)
        command = CommandEnvelope.model_validate_json(message)
        await self._incoming.put(self._reply.replace("{id}", command.id))


async def _send(reply: str, **kwargs: float) -> object:
    bridge = Bridge(BridgeConfig(), connector=connector_for(_RawReplyConnection(reply)))
    await bridge.connect()
    try:
        return await asyncio.wait_for(bridge.send("cmd_boom", {}, **kwargs), 2.0)
    finally:
        await bridge.close()


async def test_ok_less_reply_resolves_as_internal_error_without_waiting() -> None:
    response = await _send(json.dumps({"id": "{id}"}))
    assert response.ok is False  # type: ignore[attr-defined]
    assert response.error == ErrorCode.INTERNAL_ERROR  # type: ignore[attr-defined]
    assert "editor Output" in (response.hint or "")  # type: ignore[attr-defined]


async def test_malformed_reply_without_a_pending_id_is_still_dropped() -> None:
    """No id to correlate: nothing to resolve, so the request times out as before."""
    response = await _send(json.dumps({"ok": True}), timeout=0.2)
    assert response.error == ErrorCode.TIMEOUT  # type: ignore[attr-defined]


async def test_non_json_reply_is_dropped() -> None:
    response = await _send("not json {id}", timeout=0.2)
    assert response.error == ErrorCode.TIMEOUT  # type: ignore[attr-defined]
