"""Structured (JSON) logging for the MCP server (issue #4).

Logs are emitted as one JSON object per line to **stderr**. Under the stdio
transport, stdout is the MCP protocol channel — writing logs there would corrupt
it — so logging must never touch stdout (see .opencode/rules/error-handling.md for
the structured-logging requirement).
"""

from __future__ import annotations

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
