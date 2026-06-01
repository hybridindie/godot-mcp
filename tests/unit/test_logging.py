"""Unit tests for structured logging setup (issue #4)."""

from __future__ import annotations

import json
import logging
import sys

from mcp_server.logging_setup import (
    JsonFormatter,
    _is_json_stderr_handler,
    configure_logging,
)


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

    assert sys.stdout not in streams, "logging must never write to stdout"


def test_configure_logging_is_idempotent() -> None:

    configure_logging("INFO")
    count = sum(1 for h in logging.getLogger().handlers if _is_json_stderr_handler(h))
    configure_logging("INFO")
    recount = sum(1 for h in logging.getLogger().handlers if _is_json_stderr_handler(h))
    assert recount == count == 1, "repeated calls must not stack duplicate handlers"


def test_configure_logging_removes_only_stdout_handlers() -> None:

    root = logging.getLogger()
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    unrelated = logging.StreamHandler(stream=sys.stderr)  # not our JSON handler
    root.addHandler(stdout_handler)
    root.addHandler(unrelated)
    try:
        configure_logging("INFO")
        assert stdout_handler not in root.handlers, "stdout handler must be removed"
        assert unrelated in root.handlers, "unrelated handlers must be left in place"
    finally:
        root.removeHandler(unrelated)
