"""Async WebSocket client to the Godot addon — the one path Python uses to talk
to Godot (issue #3).

Every request carries an ``id`` and resolves to its own correlated response;
many may be in flight concurrently. Timeouts and reconnect backoff are driven by
an injected ``sleep`` so behaviour is deterministic under test
(see .claude/rules/async-patterns.md). A failed or absent connection yields a
structured ``ResponseEnvelope`` (``BRIDGE_DISCONNECTED`` / ``TIMEOUT``), never an
exception escaping to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from mcp_server.backoff import BackoffPolicy, compute_delay
from mcp_server.config import BridgeConfig
from mcp_server.models.envelope import CommandEnvelope, ErrorCode, ResponseEnvelope

logger = logging.getLogger(__name__)


class Connection(Protocol):
    """The minimal transport the bridge needs (a WebSocket connection)."""

    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


Connector = Callable[[str], Awaitable[Connection]]
Sleep = Callable[[float], Awaitable[None]]


async def _default_connector(url: str) -> Connection:
    # Imported lazily so importing this module performs no I/O and does not hard
    # require the websockets package until an actual connection is made.
    from websockets.asyncio.client import connect

    return await connect(url)


class Bridge:
    """A reconnecting, request/response WebSocket client to the addon."""

    def __init__(
        self,
        config: BridgeConfig | None = None,
        *,
        connector: Connector | None = None,
        sleep: Sleep = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        policy: BackoffPolicy | None = None,
    ) -> None:
        self._config = config or BridgeConfig()
        self._connector = connector or _default_connector
        self._sleep = sleep
        self._rand = rand
        self._policy = policy or BackoffPolicy()
        self._conn: Connection | None = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[ResponseEnvelope]] = {}
        self._counter = 0

    @property
    def connected(self) -> bool:
        return self._conn is not None

    async def connect(self) -> None:
        """Open a single connection and start the response reader."""
        self._conn = await self._connector(self._config.url)
        self._reader = asyncio.create_task(self._read_loop(self._conn))
        logger.debug("bridge connected", extra={"url": self._config.url})

    async def connect_with_retry(self, max_attempts: int | None = None) -> None:
        """Connect, retrying on failure with exponential backoff + full jitter."""
        attempt = 0
        while True:
            try:
                await self.connect()
                return
            except (ConnectionError, OSError, TimeoutError):
                attempt += 1
                if max_attempts is not None and attempt >= max_attempts:
                    logger.error("bridge connect gave up", extra={"attempts": attempt})
                    raise
                delay = compute_delay(self._policy, attempt - 1, self._rand())
                logger.debug("bridge reconnect", extra={"attempt": attempt, "delay": delay})
                await self._sleep(delay)

    async def close(self) -> None:
        """Close the connection and fail any in-flight requests."""
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        self._fail_pending("BRIDGE_DISCONNECTED", "Bridge closed.")

    async def send(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ResponseEnvelope:
        """Send a command and await its correlated response.

        Returns a structured ``ResponseEnvelope`` for every outcome — including
        a disconnected bridge or a timed-out request — never raising.
        """
        if self._conn is None:
            return ResponseEnvelope.failure(
                "-", ErrorCode.BRIDGE_DISCONNECTED, "Godot bridge is not connected."
            )

        msg_id = self._next_id()
        envelope = CommandEnvelope(id=msg_id, command=command, params=params or {})
        future: asyncio.Future[ResponseEnvelope] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future

        try:
            await self._conn.send(envelope.model_dump_json())
        except Exception:
            # The transport dropped mid-send: don't leak the waiter or raise.
            self._pending.pop(msg_id, None)
            if not future.done():
                future.cancel()
            self._conn = None
            self._fail_pending("BRIDGE_DISCONNECTED", "Bridge connection lost.")
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
            logger.debug("bridge reader stopped; connection closed")
            self._conn = None
            self._fail_pending("BRIDGE_DISCONNECTED", "Bridge connection lost.")

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
