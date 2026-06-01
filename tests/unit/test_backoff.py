"""Unit tests for the reconnect backoff policy (issue #3)."""

from __future__ import annotations

from mcp_server.backoff import BackoffPolicy, compute_delay


def test_base_delay_grows_exponentially() -> None:
    policy = BackoffPolicy(initial=0.2, factor=2.0, maximum=10.0)
    assert policy.base_delay(0) == 0.2
    assert policy.base_delay(1) == 0.4
    assert policy.base_delay(2) == 0.8


def test_base_delay_is_capped() -> None:
    policy = BackoffPolicy(initial=0.2, factor=2.0, maximum=1.0)
    assert policy.base_delay(10) == 1.0


def test_compute_delay_applies_full_jitter() -> None:
    policy = BackoffPolicy(initial=1.0, factor=2.0, maximum=100.0)
    # Full jitter scales the base delay by a [0, 1) random factor.
    assert compute_delay(policy, attempt=0, rand=0.0) == 0.0
    assert compute_delay(policy, attempt=0, rand=0.5) == 0.5
    assert compute_delay(policy, attempt=1, rand=1.0) == 2.0
