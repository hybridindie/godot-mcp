"""Pure transport helpers for the bridge (#829).

Extracted from ``bridge.py`` after the #801 review: the ``Bridge`` class stays
whole (it is cohesive around peer adoption + request correlation), but these
three module-level pieces are independent of its state and deserve direct tests.

Nothing here touches the event loop's shared state: ``bind_target`` parses a URL,
``supplied_token`` parses one inbound frame, and ``default_serve`` is the
websockets listener factory.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlparse

DEFAULT_BRIDGE_PORT = 9080


class Connection(Protocol):
    """The transport methods a peer must offer (the addon connection, or a fake)."""

    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


class Server(Protocol):
    """The minimal listener handle the bridge needs (what ``serve`` returns)."""

    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...


def bind_target(url: str) -> tuple[str, int]:
    """Host/port to bind from the configured bridge URL.

    ``localhost`` is normalised to ``127.0.0.1`` so the addon's IPv4 connect can
    never miss an IPv6-only listener.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    return host, parsed.port or DEFAULT_BRIDGE_PORT


def supplied_token(raw: str | bytes) -> tuple[str, bool]:
    """The token a peer's auth envelope carries, and whether it IS an auth envelope.

    The auth message is ``{id, command: cmd_auth, params: {token}}`` — the
    addon's first message when it is configured with a token (issue #538).
    Any other shape reports ``("", False)`` so the handshake loop can skip it
    (a control message racing ahead of the auth envelope) instead of falsely
    refusing.
    """
    try:
        payload: Any = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "", False
    if not isinstance(payload, dict):
        return "", False
    params = payload.get("params")
    if payload.get("command") != "cmd_auth" or not isinstance(params, dict):
        return "", False
    return str(params.get("token", "")), True


async def default_serve(
    handler: Callable[[Connection], Awaitable[None]],
    host: str,
    port: int,
    max_size: int,
) -> Server:
    """Open the real websockets listener (imported lazily so import performs no I/O)."""
    from websockets.asyncio.server import serve

    async def _on_connect(ws: Any) -> None:
        await handler(ws)

    # #563: max_size must exceed the largest frame the addon sends — the library
    # default (1 MiB) silently drops full-screenshot responses (over the wire the
    # addon sees a closed connection and just reconnects; the tool times out).
    # #636: origins=[None] rejects any handshake carrying a browser Origin (a page
    # the user visits can reach ws://127.0.0.1:9080 — WebSockets are exempt from
    # same-origin policy). The Godot addon's WebSocketPeer sends no Origin, so it
    # still connects.
    return await serve(_on_connect, host, port, max_size=max_size, origins=[None])
