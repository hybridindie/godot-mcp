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

from mcp_server.bridge import Connection
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope

# A responder maps a received command to a response, or None to stay silent
# (used to drive timeout behaviour deterministically).
Responder = Callable[[CommandEnvelope], ResponseEnvelope | None]


def _default_base_responder(
    command: CommandEnvelope, *, godot_version: str = "4.4.1-stable"
) -> ResponseEnvelope | None:
    """Handle commands every fake should support so the server can bootstrap."""
    if command.command == "cmd_ping":
        return ResponseEnvelope.success(command.id, {"pong": True})
    if command.command == "cmd_get_project_info":
        return ResponseEnvelope.success(
            command.id,
            {
                "name": "TestProject",
                "godot_version": godot_version,
                "main_scene": "res://main.tscn",
                "project_path": "/tmp/test_project",
                "autoloads": {},
                "input_actions": [],
            },
        )
    return None


def ping_responder(command: CommandEnvelope) -> ResponseEnvelope | None:
    """Default addon behaviour: answer ``cmd_ping`` with ``{pong: true}``."""
    base = _default_base_responder(command)
    if base is not None:
        return base
    return ResponseEnvelope.failure(
        command.id, "VALIDATION_ERROR", f"Unknown command '{command.command}'."
    )


class FakeAddonConnection:
    """An in-memory Connection that plays the addon side of the bridge."""

    def __init__(
        self, responder: Responder = ping_responder, *, send_error: Exception | None = None
    ) -> None:
        self._responder = responder
        self._send_error = send_error
        self._incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        if self._send_error is not None:
            raise self._send_error
        self.sent.append(message)
        command = CommandEnvelope.model_validate_json(message)
        response = self._responder(command)
        # Auto-respond to bootstrap commands the custom responder explicitly
        # doesn't know (VALIDATION_ERROR / "Unknown command"), so tests don't
        # have to repeat cmd_ping / cmd_get_project_info in every responder.
        if (
            response is not None
            and not response.ok
            and response.error == "VALIDATION_ERROR"
            and command.command in ("cmd_ping", "cmd_get_project_info")
        ):
            base = _default_base_responder(command)
            if base is not None:
                response = base
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
    """A bridge connector that yields the given fake addon peer — i.e. the addon
    connecting to the (now server-side) bridge listener. ``serve()``/``connect()``
    attach it, so contract tests exercise a connected bridge with no socket."""

    async def _connect(url: str) -> FakeAddonConnection:
        return connection

    return _connect


class _NullServer:
    """A listener handle no addon ever connects to (stays disconnected)."""

    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...


async def null_serve(
    handler: Callable[[Connection], Awaitable[None]], host: str, port: int
) -> _NullServer:
    """A ``serve`` that binds nothing and accepts no peer — for the 'editor absent'
    case (the bridge listens but stays disconnected), with no real socket."""
    return _NullServer()


async def immediate_sleep(_seconds: float) -> None:
    """A no-op sleep so timeout/backoff paths run without real waiting."""
    return None


def make_addon_responder(
    *,
    godot_version: str = "4.4.1-stable",
    project_name: str = "TestProject",
    main_scene: str = "res://main.tscn",
) -> Responder:
    """Build a responder that handles ``cmd_get_project_info`` and ``cmd_ping``.

    Other commands return a generic failure so tests can opt-in to the commands
    they care about.
    """

    def _responder(command: CommandEnvelope) -> ResponseEnvelope | None:
        if command.command == "cmd_ping":
            return ResponseEnvelope.success(command.id, {"pong": True})
        if command.command == "cmd_get_project_info":
            return ResponseEnvelope.success(
                command.id,
                {
                    "name": project_name,
                    "godot_version": godot_version,
                    "main_scene": main_scene,
                    "project_path": "/tmp/test_project",
                    "autoloads": {},
                    "input_actions": [],
                },
            )
        return ResponseEnvelope.failure(
            command.id, "VALIDATION_ERROR", f"Unknown command '{command.command}'."
        )

    return _responder
