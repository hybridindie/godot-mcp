"""Structured (JSON) logging for the MCP server (issue #4).

Logs are emitted as one JSON object per line to **stderr**. Under the stdio
transport, stdout is the MCP protocol channel — writing logs there would corrupt
it — so logging must never touch stdout (see .claude/rules/error-handling.md for
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


def configure_logging(level: str = "INFO") -> None:
    """Install a JSON stderr handler on the root logger (idempotent)."""
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
