"""Unit tests for the #572 benign-proactor-error demotion.

On Windows + ProactorEventLoop, a stdio/HTTP peer closing its end mid-shutdown
makes CPython's ``_ProactorBasePipeTransport._call_connection_lost`` raise
``ConnectionResetError`` (WinError 10054) inside the loop's exception handler —
a known-benign CPython race (the peer is gone; shutdown(SHUT_RDWR) then fails).
CPython logs it at ERROR via ``asyncio``'s default handler, which floods the
JSON stderr log every time a client (or the stdio pipe) disconnects.

The installed handler:
- recognizes exactly this signature (proactor transport + ConnectionResetError
  from ``_call_connection_lost``) and logs it at DEBUG instead of ERROR;
- leaves every other error's default behavior intact (logged at ERROR).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from mcp_server.logging_setup import (
    install_proactor_reset_demotion,
    is_benign_proactor_reset,
)


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_loop() -> asyncio.AbstractEventLoop:
    # The demotion works on any loop type; tests inject a real (non-running)
    # loop rather than spinning a proactor (deterministic, no OS dependency).
    return asyncio.new_event_loop()


@pytest.fixture()
def _asyncio_debug_level() -> Any:
    """The ``asyncio`` logger defaults to WARNING; DEBUG records need the
    logger opened up (as the server's configure_logging('DEBUG') would)."""
    logger = logging.getLogger("asyncio")
    old = logger.level
    logger.setLevel(logging.DEBUG)
    yield logger
    logger.setLevel(old)


def test_benign_signature_matches_proactor_connection_reset() -> None:
    context = {
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
        "exception": ConnectionResetError(10054, "An existing connection was forcibly closed"),
    }
    assert is_benign_proactor_reset(context) is True


def test_other_errors_are_not_benign() -> None:
    # Different exception type.
    assert (
        is_benign_proactor_reset(
            {"message": "Exception in callback", "exception": ValueError("x")}
        )
        is False
    )
    # ConnectionResetError but NOT from the proactor pipe transport teardown.
    assert (
        is_benign_proactor_reset(
            {"message": "Exception in callback _read_ready()", "exception": ConnectionResetError()}
        )
        is False
    )
    # Missing pieces.
    assert is_benign_proactor_reset({}) is False
    assert is_benign_proactor_reset({"exception": ConnectionResetError()}) is False


def test_handler_demotes_benign_reset_to_debug(_asyncio_debug_level: Any) -> None:
    """The known-benign error is logged at DEBUG (suppressed at INFO), not ERROR."""
    loop = _make_loop()
    logger = logging.getLogger("asyncio")
    handler = _RecordingHandler()
    logger.addHandler(handler)
    try:
        install_proactor_reset_demotion(loop)
        loop.call_exception_handler(
            {
                "message": "Exception in callback _ProactorBasePipeTransport"
                "._call_connection_lost()",
                "exception": ConnectionResetError(10054, "forcibly closed"),
            }
        )
        loop.stop()
        loop.run_forever()
        errors = [r for r in handler.records if r.levelno == logging.ERROR]
        debugs = [r for r in handler.records if r.levelno == logging.DEBUG]
        assert errors == [], f"benign reset must not log at ERROR: {errors}"
        assert debugs, "benign reset should be logged at DEBUG for diagnosability"
        assert any(
            "_call_connection_lost" in r.getMessage()
            or "connection reset" in r.getMessage().lower()
            for r in debugs
        ), [r.getMessage() for r in debugs]
    finally:
        logger.removeHandler(handler)
        loop.close()


def test_handler_keeps_other_errors_at_error_level(_asyncio_debug_level: Any) -> None:
    """A genuinely unexpected loop error keeps the default ERROR treatment."""
    loop = _make_loop()
    logger = logging.getLogger("asyncio")
    handler = _RecordingHandler()
    logger.addHandler(handler)
    try:
        install_proactor_reset_demotion(loop)
        loop.call_exception_handler(
            {"message": "Fatal error on transport", "exception": ValueError("real bug")}
        )
        loop.stop()
        loop.run_forever()
        errors = [r for r in handler.records if r.levelno == logging.ERROR]
        assert len(errors) == 1, [r.getMessage() for r in handler.records]
    finally:
        logger.removeHandler(handler)
        loop.close()


def test_handler_does_not_swallow_context_without_exception(_asyncio_debug_level: Any) -> None:
    """A benign-shaped context missing the exception is still logged normally."""
    loop = _make_loop()
    logger = logging.getLogger("asyncio")
    handler = _RecordingHandler()
    logger.addHandler(handler)
    try:
        install_proactor_reset_demotion(loop)
        loop.call_exception_handler({"message": "Exception in callback _call_connection_lost()"})
        loop.stop()
        loop.run_forever()
        assert len(handler.records) >= 1, "a context without an exception is not demoted away"
    finally:
        logger.removeHandler(handler)
        loop.close()


def test_install_is_idempotent(_asyncio_debug_level: Any) -> None:
    """Installing twice replaces the handler, never stacks duplicates."""
    loop = _make_loop()
    logger = logging.getLogger("asyncio")
    handler = _RecordingHandler()
    logger.addHandler(handler)
    try:
        install_proactor_reset_demotion(loop)
        install_proactor_reset_demotion(loop)
        benign = {
            "message": "Exception in callback _ProactorBasePipeTransport"
            "._call_connection_lost()",
            "exception": ConnectionResetError(10054, "forcibly closed"),
        }
        loop.call_exception_handler(benign)
        loop.stop()
        loop.run_forever()
        debugs = [r for r in handler.records if r.levelno == logging.DEBUG]
        assert len(debugs) == 1, [r.getMessage() for r in handler.records]
    finally:
        logger.removeHandler(handler)
        loop.close()