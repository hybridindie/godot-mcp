"""WebSocket bridge to the Godot addon — the one path Python uses to talk to Godot
(issue #3; direction inverted in #276).

The MCP server is the **listener**: ``serve()`` binds the bridge port and waits for the
Godot addon (now the WebSocket *client*) to connect and reconnect to it. The editor is
the party that comes and goes, so it owns reconnection (see docs/architecture.md). A new
peer connection replaces the old one; the server keeps at most one active peer.

Every request carries an ``id`` and resolves to its own correlated response; many may be
in flight concurrently. Timeouts are driven by an injected ``sleep`` so behaviour is
deterministic under test (see .opencode/rules/async-patterns.md). A failed or absent peer
yields a structured ``ResponseEnvelope`` (``BRIDGE_DISCONNECTED`` / ``TIMEOUT``), never
an exception escaping to the caller.

Tests inject a ``connector`` (a source for the fake addon peer); ``serve()``/``connect()``
then *attach* that peer instead of binding a socket, so the envelope contract can be
exercised with no editor and no sockets.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol
from urllib.parse import urlparse

from mcp_server import __version__
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
# ``max_size`` is the inbound message cap the real listener must apply (#563).
Serve = Callable[
    [Callable[[Connection], Awaitable[None]], str, int, int], Awaitable[Server]
]
Sleep = Callable[[float], Awaitable[None]]


def _bind_target(url: str) -> tuple[str, int]:
    """Host/port to bind from the configured bridge URL. ``localhost`` is normalised to
    ``127.0.0.1`` so the addon's IPv4 connect can never miss an IPv6-only listener."""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    return host, parsed.port or 9080


def _supplied_token(raw: str | bytes) -> tuple[str, bool]:
    """The token a peer's auth envelope carries, and whether it IS an auth envelope.

    The auth message is ``{id, command: cmd_auth, params: {token}}`` — the
    addon's first message when it is configured with a token (issue #538).
    Any other shape reports ``(, False)`` so the handshake loop can skip it
    (a control message racing ahead of the auth envelope) instead of falsely
    refusing."""
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


async def _default_serve(
    handler: Callable[[Connection], Awaitable[None]],
    host: str,
    port: int,
    max_size: int,
) -> Server:
    # Imported lazily so importing this module performs no I/O and does not hard-require
    # the websockets package until the listener is actually started.
    from websockets.asyncio.server import serve

    async def _on_connect(ws: Any) -> None:
        await handler(ws)

    # #563: max_size must exceed the largest frame the addon sends — the library
    # default (1 MiB) silently drops full-screenshot responses (over the wire the
    # addon sees a closed connection and just reconnects; the tool times out).
    return await serve(_on_connect, host, port, max_size=max_size)


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
        # Server↔addon handshake cache (issue #530): the addon's self-description
        # from cmd_get_addon_info, fetched lazily on first use and reset whenever
        # the peer changes (a new editor = a new handshake). Dict or None.
        self._addon_info: dict[str, Any] | None = None
        # Serialises the lazy handshake so two concurrent addon_info() callers
        # can't both see an empty cache and both send the handshake (Qodo
        # review on PR #543: duplicate cmd_server_hello pushes otherwise).
        self._addon_info_lock = asyncio.Lock()
        # Peer identity (issue #537): the hello the addon sends right after
        # connecting (project_path / godot_version / addon_version). None when
        # the peer predates the hello (older addon) — identity-unknown, never
        # an error. Reset whenever the peer changes.
        self._peer_identity: dict[str, Any] | None = None
        # Bridge auth (issue #538): when a token is configured, each adopted peer
        # must authenticate before the bridge serves it. True once THIS peer
        # authenticated; reset whenever the peer changes.
        self._authed = False
        # Count of peer connection attempts (auth'd or refused) — diagnostics +
        # e2e polling: a refused peer (auth mismatch) never flips ``connected``,
        # so the e2e asserts on this instead.
        self.peer_attempts = 0
        # #563: the inbound message cap handed to the real listener (the injected
        # test ``serve`` ignores it — fakes have no transport limits to drop a frame).
        self._max_inbound_message_bytes = self._config.max_inbound_message_bytes

    @property
    def connected(self) -> bool:
        return self._conn is not None

    @property
    def url(self) -> str:
        return self._config.url

    @property
    def peer_identity(self) -> dict[str, Any] | None:
        """The connected editor's announced identity (issue #537), or None.

        ``{project_path, godot_version, addon_version}`` once the hello landed;
        ``None`` = an older addon without the hello (identity unknown).
        """
        return self._peer_identity

    async def adopt_identity(self, identity: dict[str, Any]) -> None:
        """Record the connected peer's announced identity (issue #537).

        Called from the read loop when a ``cmd_peer_hello`` envelope arrives
        (and from tests). The replacement event itself is logged in ``_attach``
        (naming the old path); this records the new identity and logs it.
        """
        self._peer_identity = dict(identity or {})
        logger.info(
            "bridge peer identity",
            extra={"project_path": str((identity or {}).get("project_path", ""))},
        )

    async def addon_info(self) -> dict[str, Any] | None:
        """The connected addon's self-description (issue #530), or None.

        Lazily calls ``cmd_get_addon_info`` once per peer and caches the result:
        ``{ addon_version, godot_version, commands: [cmd_*] }``. Returns None when
        the addon is unreachable or predates the handshake (older addon), so
        callers degrade gracefully instead of failing.

        On the first successful handshake, pushes the server's package version
        back to the addon via ``cmd_server_hello`` (issue #521) — fire-and-forget,
        so the addon's dock can label the connection with both versions.

        Serialised by ``_addon_info_lock`` so concurrent callers see exactly one
        handshake per peer (the lock is only taken while the cache is empty —
        steady-state reads are lock-free).
        """
        if self._conn is None:
            return None
        if self._addon_info is None:
            async with self._addon_info_lock:
                # Double-check inside the lock: the first caller through may
                # have completed the handshake while we awaited the lock.
                if self._addon_info is None:
                    response = await self.send("cmd_get_addon_info", timeout=5.0)
                    if response.ok and isinstance(response.result, dict):
                        self._addon_info = response.result
                        # Best-effort push (issue #521): an old addon that lacks
                        # cmd_server_hello answers "Unknown command" — ignored
                        # here, the dock just keeps showing the Godot version.
                        await self.send(
                            "cmd_server_hello", {"version": __version__}, timeout=5.0
                        )
        return self._addon_info

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
        self._server = await self._serve(
            self._handle_peer, host, port, self._max_inbound_message_bytes
        )
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
                # #537: a replaced peer is never silent — the log names both
                # project paths (or "unknown" when the old peer predated the
                # hello), so the first editor's agent can see WHY it went dark.
                old_path = str((self._peer_identity or {}).get("project_path", ""))
                logger.info(
                    "bridge peer replaced",
                    extra={
                        "previous_peer": old_path or "(unknown)",
                        "new_peer": "(pending hello)",
                    },
                )
            # A new peer is a new addon: the cached handshake no longer describes it.
            self._addon_info = None
            # ...and neither does its announced identity (#537): the replacement
            # itself is logged at replacement time (above), the new identity
            # lands when its hello arrives.
            self._peer_identity = None
            # ...and it must authenticate again (#538): auth state never leaks
            # from one connection to the next.
            self._authed = False
        self.peer_attempts += 1
        # Bridge auth handshake (issue #538): with a token configured, the peer's
        # FIRST message must authenticate it. A refusal happens here — at the
        # handshake, structured, never as a per-command error — and the peer is
        # dropped immediately (the addon's reconnect/backoff loop then retries,
        # showing the refusal reason in the dock log).
        pre_auth: list[str | bytes] = []
        if self._config.auth_token is not None:
            ok, pre_auth = await self._auth_check(conn)
            if not ok:
                return
        self._conn = conn
        # Control messages the handshake consumed ahead of the auth envelope
        # (e.g. the #537 peer hello pipelined alongside it) still belong to the
        # read loop — replay them so identity handling isn't skipped.
        for raw in pre_auth:
            self._resolve(raw if isinstance(raw, str) else raw.decode("utf-8"))
        self._reader = asyncio.create_task(self._read_loop(conn))
        logger.debug("bridge peer connected")

    async def _auth_check(self, conn: Connection) -> tuple[bool, list[str | bytes]]:
        """Require + verify the peer's auth envelope before adoption (issue #538).

        The addon sends ``{id, command: cmd_auth, params: {token}}`` as its first
        message when configured with a token. Within the handshake budget the
        check consumes up to a few messages and picks the FIRST ``cmd_auth``
        envelope — so a peer that pipelines its identity hello (or other control
        messages) alongside the auth can never have the hello consumed as the
        auth message (a false refusal; PR #558 review). Skipped control messages
        are returned for replay into the read loop. A missing/wrong token
        answers a structured refusal envelope, drops the peer, and returns
        False. Comparison is constant-time (``hmac.compare_digest``); the token
        is never logged.
        """
        expected = self._config.auth_token
        if expected is None:
            return True, []
        # A short handshake budget: the addon sends auth right after the
        # websocket opens (or never — that's the refusal case). A full request
        # timeout here would stall the listener on a silent peer.
        deadline = asyncio.get_running_loop().time() + min(
            2.0, self._config.request_timeout
        )
        skipped: list[str | bytes] = []
        while True:
            try:
                raw = await asyncio.wait_for(
                    conn.recv(), timeout=max(0.0, deadline - asyncio.get_running_loop().time())
                )
            except (TimeoutError, Exception) as exc:  # noqa: BLE001 — see hint text
                if isinstance(exc, asyncio.CancelledError):
                    raise  # never swallow shutdown cancellation
                logger.warning("bridge auth: no auth message from peer; refusing")
                with suppress(Exception):
                    await conn.close()
                return False, []
            supplied, is_auth = _supplied_token(raw)
            if not is_auth:
                skipped.append(raw)  # replay after adoption (identity, etc.)
                continue
            if not hmac.compare_digest(supplied, expected):
                # Structured refusal at the handshake (never per-command, never
                # silent). The token itself is never logged.
                logger.warning("bridge auth: token mismatch; refusing peer")
                with suppress(Exception):
                    await conn.send(
                        ResponseEnvelope.failure(
                            "auth",
                            ErrorCode.VALIDATION_ERROR,
                            "Bridge auth failed: the GODOT_MCP_BRIDGE_TOKEN this editor sent does "
                            "not match the server's. Fix the env var on one side; reconnecting "
                            "will keep failing until they match.",
                            "bridge_token",
                        ).model_dump_json()
                    )
                with suppress(Exception):
                    await conn.close()
                return False, []
            self._authed = True
            logger.info("bridge peer authenticated")
            return True, skipped

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
        self._addon_info = None
        self._peer_identity = None

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
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("dropping unparseable bridge message")
            return
        # Peer identity hello (issue #537): a control message, not a response —
        # no waiter exists for it, so it must be consumed here rather than
        # falling through to the malformed-reply path.
        if isinstance(payload, dict) and payload.get("command") == "cmd_peer_hello":
            params = payload.get("params")
            if isinstance(params, dict):
                self._peer_identity = dict(params)
                logger.info(
                    "bridge peer identity",
                    extra={"project_path": str(params.get("project_path", ""))},
                )
            return
        try:
            response = ResponseEnvelope.model_validate(payload)
        except ValueError:
            self._fail_malformed(payload)
            return
        future = self._pending.pop(response.id, None)
        if future is not None and not future.done():
            future.set_result(response)

    def _fail_malformed(self, payload: Any) -> None:
        """Answer a reply that isn't a valid envelope but still names a waiting request.

        The addon did reply (typically a handler that hit a GDScript error), so the caller
        gets ``INTERNAL_ERROR`` now instead of waiting out the request timeout (#466).
        """
        msg_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(msg_id, str) or (future := self._pending.pop(msg_id, None)) is None:
            logger.error("dropping unparseable bridge message")
            return
        logger.error("malformed response envelope", extra={"id": msg_id})
        if not future.done():
            future.set_result(
                ResponseEnvelope.failure(
                    msg_id,
                    ErrorCode.INTERNAL_ERROR,
                    "Godot replied without a valid response envelope; the addon handler "
                    "most likely hit a GDScript error (see the editor Output panel).",
                )
            )

    def _fail_pending(self, error: str, hint: str) -> None:
        for msg_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(ResponseEnvelope.failure(msg_id, error, hint))
        self._pending.clear()

    def _next_id(self) -> str:
        self._counter += 1
        return str(self._counter)
