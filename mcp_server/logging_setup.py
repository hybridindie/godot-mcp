"""Structured (JSON) logging for the MCP server (issue #4).

Logs are emitted as one JSON object per line to **stderr**. Under the stdio
transport, stdout is the MCP protocol channel — writing logs there would corrupt
it — so logging must never touch stdout (see .opencode/rules/error-handling.md for
the structured-logging requirement).

Also installs the #572 loop-exception demotion: on Windows' ProactorEventLoop a
peer closing its end mid-shutdown makes CPython's pipe-transport teardown raise
``ConnectionResetError`` (WinError 10054) and CPython's default handler logs it
at ERROR on the ``asyncio`` logger — benign noise on every client disconnect
(see :func:`install_proactor_reset_demotion`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

# Standard LogRecord attributes, so we can surface any extra structured fields.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Format a log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include structured extras passed via logging's ``extra=`` (e.g. the
        # bridge command id), and exception info when present.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _is_json_stderr_handler(handler: logging.Handler) -> bool:
    return isinstance(handler.formatter, JsonFormatter) and (
        getattr(handler, "stream", None) is sys.stderr
    )


def configure_logging(level: str = "INFO") -> None:
    """Route root logging to a JSON stderr handler.

    Idempotent and non-destructive: removes only stdout-bound handlers (which would
    corrupt the stdio MCP channel) and installs our stderr JSON handler at most
    once, leaving any unrelated handlers in place.
    """
    root = logging.getLogger()

    # Drop any handler writing to stdout — stdout is the stdio protocol channel.
    for handler in list(root.handlers):
        if getattr(handler, "stream", None) is sys.stdout:
            root.removeHandler(handler)

    if not any(_is_json_stderr_handler(h) for h in root.handlers):
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)

    root.setLevel(level.upper())


# --- #572: benign Windows proactor ConnectionResetError demotion -------------

_BENIGN_PROACTOR_CALLBACK = "_ProactorBasePipeTransport._call_connection_lost"


def is_benign_proactor_reset(context: dict[str, Any]) -> bool:
    """True for the known-benign CPython proactor teardown race (#572): a peer
    closing its end mid-shutdown makes ``_call_connection_lost``'s
    ``shutdown(SHUT_RDWR)`` raise ``ConnectionResetError`` (WinError 10054).
    The connection is already gone; nothing is recoverable and nothing failed."""
    exception = context.get("exception")
    if not isinstance(exception, ConnectionResetError):
        return False
    message = str(context.get("message", ""))
    return _BENIGN_PROACTOR_CALLBACK in message


def _previous_handler(loop: asyncio.AbstractEventLoop) -> Any:
    """The handler installed before ours (None = CPython's default)."""
    handler = loop.get_exception_handler()
    return getattr(handler, "_previous_handler", None) if handler is not None else None


def install_proactor_reset_demotion(loop: asyncio.AbstractEventLoop) -> None:
    """Route the known-benign proactor ``ConnectionResetError`` to DEBUG.

    Wraps the loop's existing exception handler: the benign signature is logged
    at DEBUG on the ``asyncio`` logger (with the exception detail, for
    diagnosability), everything else — including the same callback with a
    different exception, and every unrelated loop error — goes to the previous
    handler (or CPython's default ERROR treatment). Installing twice replaces
    the handler (idempotent); installing on a non-Proactor loop is harmless
    (the signature can only be produced by the Windows proactor transports).
    """
    previous = loop.get_exception_handler()

    def _handler(
        loop_: asyncio.AbstractEventLoop, context: dict[str, Any], _prev: Any = previous
    ) -> None:
        if is_benign_proactor_reset(context):
            logging.getLogger("asyncio").debug(
                "benign proactor ConnectionResetError on pipe teardown "
                "(peer closed mid-shutdown; WinError 10054) — %s",
                context.get("message", ""),
                exc_info=context.get("exception"),
            )
            return
        if _prev is not None:
            _prev(loop_, context)
            return
        loop_.default_exception_handler(context)

    loop.set_exception_handler(_handler)
