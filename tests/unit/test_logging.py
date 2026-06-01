"""Unit tests for structured logging setup (issue #4)."""

from __future__ import annotations

import json
import logging

from mcp_server.logging_setup import JsonFormatter, configure_logging


def test_json_formatter_emits_parseable_record() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="mcp_server.bridge",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="bridge connected",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "mcp_server.bridge"
    assert payload["message"] == "bridge connected"


def test_configure_logging_does_not_touch_stdout() -> None:
    # stdio transport uses stdout for the MCP protocol; logs must go to stderr.
    configure_logging("INFO")
    handlers = logging.getLogger().handlers
    assert handlers, "configure_logging must install a handler"
    streams = [getattr(h, "stream", None) for h in handlers]
    import sys

    assert sys.stdout not in streams, "logging must never write to stdout"
