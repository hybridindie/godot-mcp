"""Test doubles for the WebSocket bridge (issue #3).

``FakeAddonConnection`` stands in for the Godot addon at the bridge's transport
boundary: the bridge sends a command JSON, the fake validates it, runs a
``responder`` to produce a response envelope, and queues it for ``recv()``.
This exercises the real envelope shapes and ``id`` correlation with no sockets
and no running editor (per .claude/rules/testing.md).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope

# A responder maps a received command to a response, or None to stay silent
# (used to drive timeout behaviour deterministically).
Responder = Callable[[CommandEnvelope], ResponseEnvelope | None]


def ping_responder(command: CommandEnvelope) -> ResponseEnvelope | None:
    """Default addon behaviour: answer ``ping`` with ``{pong: true}``."""
    if command.command == "ping":
        return ResponseEnvelope.success(command.id, {"pong": True})
    return ResponseEnvelope.failure(
        command.id, "VALIDATION_ERROR", f"Unknown command '{command.command}'."
    )


class FakeAddonConnection:
    """An in-memory Connection that plays the addon side of the bridge."""

    def __init__(self, responder: Responder = ping_responder) -> None:
        self._responder = responder
        self._incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)
        command = CommandEnvelope.model_validate_json(message)
        response = self._responder(command)
        if response is not None:
            await self._incoming.put(response.model_dump_json())

    async def recv(self) -> str:
        return await self._incoming.get()

    async def close(self) -> None:
        self.closed = True

    # Convenience for assertions: the most recent command the bridge sent.
    def last_command(self) -> CommandEnvelope:
        return CommandEnvelope.model_validate_json(self.sent[-1])


def connector_for(
    connection: FakeAddonConnection,
) -> Callable[[str], Awaitable[FakeAddonConnection]]:
    """A bridge connector that always returns the given fake connection."""

    async def _connect(url: str) -> FakeAddonConnection:
        return connection

    return _connect


def flaky_connector(
    fail_times: int, connection: FakeAddonConnection
) -> Callable[[str], Awaitable[FakeAddonConnection]]:
    """A connector that raises ``ConnectionError`` ``fail_times`` times, then connects.

    Drives the reconnect/backoff path deterministically.
    """
    attempts = {"n": 0}

    async def _connect(url: str) -> FakeAddonConnection:
        if attempts["n"] < fail_times:
            attempts["n"] += 1
            raise ConnectionError("addon not reachable")
        return connection

    return _connect


async def immediate_sleep(_seconds: float) -> None:
    """A no-op sleep so timeout/backoff paths run without real waiting."""
    return None

