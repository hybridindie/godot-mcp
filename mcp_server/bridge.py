"""WebSocket bridge to the Godot addon — the one path Python uses to talk to Godot
(issue #3; direction inverted in #276).

The MCP server is the **listener**: ``serve()`` binds the bridge port and waits for the
Godot addon (now the WebSocket *client*) to connect and reconnect to it. The editor is
the party that comes and goes, so it owns reconnection (see docs/architecture.md). A new
peer connection replaces the old one; the server keeps at most one active peer.

Every request carries an ``id`` and resolves to its own correlated response; many may be
in flight concurrently. Timeouts are driven by an injected ``sleep`` so behaviour is
deterministic under test (see .claude/rules/async-patterns.md). A failed or absent peer
yields a structured ``ResponseEnvelope`` (``BRIDGE_DISCONNECTED`` / ``TIMEOUT``), never
an exception escaping to the caller.

Tests inject a ``connector`` (a source for the fake addon peer); ``serve()``/``connect()``
then *attach* that peer instead of binding a socket, so the envelope contract can be
exercised with no editor and no sockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol
from urllib.parse import urlparse

from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ErrorCode, ResponseEnvelope

logger = logging.getLogger(__name__)


class Connection(Protocol):
    """The minimal transport the bridge needs (an accepted WebSocket peer)."""

    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


class Server(Protocol):
    """The minimal listener handle the bridge needs (what ``serve`` returns)."""

    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...


# A connector yields the peer to adopt (the fake addon, in tests). Production binds a
# real listener instead and adopts whatever connects, so connector is None there.
Connector = Callable[[str], Awaitable[Connection]]
# A serve function: start listening, dispatching each accepted peer to ``handler``.
Serve = Callable[[Callable[[Connection], Awaitable[None]], str, int], Awaitable[Server]]
Sleep = Callable[[float], Awaitable[None]]


def _bind_target(url: str) -> tuple[str, int]:
    """Host/port to bind from the configured bridge URL. ``localhost`` is normalised to
    ``127.0.0.1`` so the addon's IPv4 connect can never miss an IPv6-only listener."""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    return host, parsed.port or 9080


async def _default_serve(
    handler: Callable[[Connection], Awaitable[None]], host: str, port: int
) -> Server:
    # Imported lazily so importing this module performs no I/O and does not hard-require
    # the websockets package until the listener is actually started.
    from websockets.asyncio.server import serve

    async def _on_connect(ws: Any) -> None:
        await handler(ws)

    return await serve(_on_connect, host, port)


class Bridge:
    """A request/response WebSocket **listener** the Godot addon connects to."""

    def __init__(
        self,
        config: BridgeConfig | None = None,
        *,
        serve: Serve | None = None,
        connector: Connector | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._config = config or BridgeConfig()
        self._serve = serve or _default_serve
        self._connector = connector
        self._sleep = sleep
        self._server: Server | None = None
        self._conn: Connection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[ResponseEnvelope]] = {}
        self._counter = 0
        # Serialises peer adoption so two near-simultaneous editor connections can't
        # race to swap _conn/_reader and leave two readers resolving futures (#276 review).
        self._attach_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._conn is not None

    async def serve(self) -> None:
        """Start listening for the addon to connect (it is the client now). Idempotent.

        With an injected ``connector`` (tests) the peer it yields is attached directly
        instead of binding a socket — the addon "connecting" to the listener."""
        if self._connector is not None:
            await self.connect()
            return
        if self._server is not None:
            return
        host, port = _bind_target(self._config.url)
        self._server = await self._serve(self._handle_peer, host, port)
        logger.info("bridge listening", extra={"host": host, "port": port})

    async def connect(self) -> None:
        """Attach the peer from the injected ``connector`` (test/compat seam — simulates
        the addon connecting to the listener)."""
        if self._connector is None:
            raise RuntimeError("connect() requires an injected connector; production uses serve()")
        await self._attach(await self._connector(self._config.url))

    async def _handle_peer(self, conn: Connection) -> None:
        """Per-connection handler for the real listener: adopt the peer and stay until it
        disconnects, so ``websockets`` keeps the connection open for the read loop."""
        await self._attach(conn)
        reader = self._reader
        if reader is not None:
            await reader

    async def _attach(self, conn: Connection) -> None:
        """Adopt ``conn`` as the active peer, replacing and failing out any previous one,
        and start its response reader.

        Serialised by ``_attach_lock`` so concurrent editor connections can't interleave,
        and the replaced peer's reader is **fully stopped** (awaited after cancel) before
        the new one adopts ``self._conn`` — otherwise a dying read loop could resolve a
        future the new peer now owns (#276 review)."""
        async with self._attach_lock:
            if self._conn is not None:
                old, old_reader = self._conn, self._reader
                self._conn = None
                self._reader = None
                if old_reader is not None:
                    old_reader.cancel()
                    with suppress(asyncio.CancelledError):
                        await old_reader
                self._fail_pending("BRIDGE_DISCONNECTED", "Replaced by a new editor connection.")
                await old.close()
            self._conn = conn
            self._reader = asyncio.create_task(self._read_loop(conn))
            logger.debug("bridge peer connected")

    async def close(self) -> None:
        """Stop listening, drop the peer, and fail any in-flight requests.

        Runs on the lifespan-teardown path, so a Ctrl-C / shutdown can cancel the task
        while we await the peer's or listener's close. Suppress that ``CancelledError``
        so teardown still completes (server dropped, pending requests failed) instead of
        escaping as a traceback — the process is already on its way down."""
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None
        if self._conn is not None:
            with suppress(asyncio.CancelledError):
                await self._conn.close()
            self._conn = None
        if self._server is not None:
            self._server.close()
            with suppress(asyncio.CancelledError):
                await self._server.wait_closed()
            self._server = None
        self._fail_pending("BRIDGE_DISCONNECTED", "Bridge closed.")

    async def send(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ResponseEnvelope:
        """Send a command to the connected editor and await its correlated response.

        Returns a structured ``ResponseEnvelope`` for every outcome — no peer connected
        or a timed-out request included — never raising.
        """
        conn = self._conn
        if conn is None:
            return ResponseEnvelope.failure(
                "-", ErrorCode.BRIDGE_DISCONNECTED, "Godot is not connected to the bridge."
            )

        msg_id = self._next_id()
        envelope = CommandEnvelope(id=msg_id, command=command, params=params or {})
        future: asyncio.Future[ResponseEnvelope] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future

        try:
            await conn.send(envelope.model_dump_json())
        except Exception:
            # The transport dropped mid-send: don't leak the waiter or raise.
            self._pending.pop(msg_id, None)
            if not future.done():
                future.cancel()
            if self._conn is conn:
                self._conn = None
            self._fail_pending("BRIDGE_DISCONNECTED", "Editor connection lost.")
            return ResponseEnvelope.failure(
                msg_id, ErrorCode.BRIDGE_DISCONNECTED, "Lost connection to Godot while sending."
            )
        return await self._await_response(msg_id, future, timeout)

    async def ping(self) -> bool:
        """Liveness probe: ``cmd_ping`` should answer ``{pong: true}``."""
        response = await self.send("cmd_ping")
        return response.ok and bool(response.result and response.result.get("pong"))

    # --- internals -------------------------------------------------------

    async def _await_response(
        self,
        msg_id: str,
        future: asyncio.Future[ResponseEnvelope],
        timeout: float | None,
    ) -> ResponseEnvelope:
        deadline = timeout if timeout is not None else self._config.request_timeout
        timeout_task = asyncio.ensure_future(self._sleep(deadline))
        waitables: set[asyncio.Future[Any]] = {future, timeout_task}
        try:
            done, _ = await asyncio.wait(waitables, return_when=asyncio.FIRST_COMPLETED)
        finally:
            timeout_task.cancel()

        if future in done:
            return future.result()

        # Timed out: drop and cancel the waiter so it doesn't leak or warn on GC.
        self._pending.pop(msg_id, None)
        if not future.done():
            future.cancel()
        return ResponseEnvelope.failure(
            msg_id,
            ErrorCode.TIMEOUT,
            f"No response from Godot within {deadline}s; check the editor and bridge.",
        )

    async def _read_loop(self, conn: Connection) -> None:
        """Read responses and resolve their waiting futures by ``id``."""
        try:
            while True:
                raw = await conn.recv()
                self._resolve(raw if isinstance(raw, str) else raw.decode("utf-8"))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("bridge reader stopped; editor disconnected")
            if self._conn is conn:
                self._conn = None
            self._fail_pending("BRIDGE_DISCONNECTED", "Editor connection lost.")

    def _resolve(self, raw: str) -> None:
        try:
            response = ResponseEnvelope.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            logger.error("dropping unparseable bridge message")
            return
        future = self._pending.pop(response.id, None)
        if future is not None and not future.done():
            future.set_result(response)

    def _fail_pending(self, error: str, hint: str) -> None:
        for msg_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(ResponseEnvelope.failure(msg_id, error, hint))
        self._pending.clear()

    def _next_id(self) -> str:
        self._counter += 1
        return str(self._counter)
