"""Contract tests for the bridge WebSocket Origin guard (issue #636).

Browsers do not apply the same-origin policy to WebSockets, so any page the user
visits could open ``ws://127.0.0.1:9080``. The real listener must therefore
reject a handshake that carries a browser ``Origin`` header, while the Godot
addon — whose ``WebSocketPeer`` sends **no** Origin — still connects. Exercised
against a real loopback listener on an ephemeral port (the production
``_default_serve`` path the fakes bypass).
"""

from __future__ import annotations

from typing import Any

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
from websockets.typing import Origin

from mcp_server.bridge import _default_serve

pytestmark = pytest.mark.asyncio


async def _keep_open(conn: Any) -> None:
    await conn.wait_closed()


async def test_originless_handshake_succeeds_and_browser_origin_is_rejected() -> None:
    server: Any = await _default_serve(_keep_open, "127.0.0.1", 0, 1024)
    port = server.sockets[0].getsockname()[1]
    try:
        # The Godot addon's WebSocketPeer sends no Origin header — accepted.
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            assert ws is not None
        # A browser page's Origin is rejected at the handshake (403).
        with pytest.raises(InvalidStatus) as exc:
            async with connect(
                f"ws://127.0.0.1:{port}", origin=Origin("https://example.com")
            ):
                pass
        assert exc.value.response.status_code == 403
    finally:
        server.close()
        await server.wait_closed()
