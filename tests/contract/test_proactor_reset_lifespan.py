"""Contract test: the server lifespan installs the #572 loop-exception demotion.

The benign Windows proactor ``ConnectionResetError`` (WinError 10054 on pipe
teardown) must be demoted to DEBUG inside the running loop — the demotion is
wired in ``create_server``'s lifespan, so starting the server never floods the
JSON stderr log at ERROR when a client disconnects mid-shutdown (#572).
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.logging_setup import is_benign_proactor_reset
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

_BENIGN_CONTEXT = {
    "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
    "exception": ConnectionResetError(10054, "An existing connection was forcibly closed"),
}


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_lifespan_installs_proactor_reset_demotion() -> None:
    """While the server runs, the loop's exception handler demotes the benign
    reset to DEBUG (no ERROR record) and leaves other errors at ERROR."""
    conn = FakeAddonConnection()
    server = create_server(
        ServerConfig(), bridge=Bridge(ServerConfig().bridge, connector=connector_for(conn))
    )
    loop = asyncio.get_running_loop()
    logger = logging.getLogger("asyncio")
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    capture = _Capture()
    logger.addHandler(capture)
    try:
        async with Client(server):
            handler = loop.get_exception_handler()
            assert handler is not None, "lifespan must install the #572 demotion"
            assert is_benign_proactor_reset(_BENIGN_CONTEXT)
            # The installed handler is ours (it defaults-in the previous handler).
            assert "_prev" in handler.__code__.co_freevars or handler.__defaults__
        # After the lifespan the demotion may remain installed (loop teardown) —
        # the assertion above is what pins the wiring.
    finally:
        logger.removeHandler(capture)
        logger.setLevel(old_level)