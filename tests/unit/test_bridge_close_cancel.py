"""Shutdown resilience: ``Bridge.close()`` must survive a cancellation landing on the
listener's ``wait_closed()`` (a Ctrl-C / lifespan teardown), tearing the bridge down and
failing in-flight requests rather than surfacing a ``CancelledError`` traceback.
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import ErrorCode


class _CancellingServer:
    """Stand-in listener whose ``wait_closed()`` is cancelled mid-await, the way a
    Ctrl-C-driven lifespan teardown cancels the task awaiting it."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_close_tolerates_cancelled_wait_closed() -> None:
    bridge = Bridge(BridgeConfig())
    server = _CancellingServer()
    bridge._server = server  # type: ignore[assignment]
    pending: asyncio.Future[object] = asyncio.get_running_loop().create_future()
    bridge._pending["1"] = pending  # type: ignore[assignment]

    await bridge.close()  # must not raise CancelledError

    assert server.closed is True
    assert bridge._server is None
    resp = pending.result()
    assert resp.ok is False  # type: ignore[attr-defined]
    assert resp.error == ErrorCode.BRIDGE_DISCONNECTED  # type: ignore[attr-defined]
