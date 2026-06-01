"""Integration tests for bridge connect/reconnect behaviour (issue #3).

Reconnect is driven by an injected connector and sleep, so backoff is verified
deterministically — no real sockets, no wall-clock waits.
"""

from __future__ import annotations

import pytest

from mcp_server.backoff import BackoffPolicy
from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.fakes import FakeAddonConnection, flaky_connector

pytestmark = pytest.mark.asyncio


async def test_connect_with_retry_recovers_after_failures() -> None:
    conn = FakeAddonConnection()
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    bridge = Bridge(
        BridgeConfig(),
        connector=flaky_connector(fail_times=3, connection=conn),
        sleep=record_sleep,
        rand=lambda: 1.0,  # full base delay, no jitter shrink, for predictable values
        policy=BackoffPolicy(initial=0.2, factor=2.0, maximum=10.0),
    )

    await bridge.connect_with_retry()

    assert bridge.connected is True
    # Three failures ⇒ three backoff sleeps with exponentially growing delays.
    assert delays == [0.2, 0.4, 0.8]
    assert await bridge.ping() is True
    await bridge.close()


async def test_connect_with_retry_gives_up_after_max_attempts() -> None:
    conn = FakeAddonConnection()

    async def noop_sleep(_seconds: float) -> None:
        return None

    bridge = Bridge(
        BridgeConfig(),
        connector=flaky_connector(fail_times=10, connection=conn),
        sleep=noop_sleep,
    )

    with pytest.raises(ConnectionError):
        await bridge.connect_with_retry(max_attempts=2)
    assert bridge.connected is False
