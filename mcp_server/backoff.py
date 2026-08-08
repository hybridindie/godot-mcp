"""Exponential backoff with full jitter for bridge reconnect (issue #3).

Pure functions over an injected random factor so reconnect timing is
deterministic in tests (see .opencode/rules/async-patterns.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffPolicy:
    """Exponential backoff parameters. ``attempt`` is zero-based."""

    initial: float = 0.2
    factor: float = 2.0
    maximum: float = 10.0

    def base_delay(self, attempt: int) -> float:
        """The capped, un-jittered delay for a given retry attempt."""
        return min(self.maximum, self.initial * (self.factor**attempt))


def compute_delay(policy: BackoffPolicy, attempt: int, rand: float) -> float:
    """Apply full jitter: scale the base delay by ``rand`` in ``[0, 1]``.

    ``random.random()`` supplies ``[0, 1)`` in production; tests pass ``1.0`` to
    assert the un-jittered base. Full jitter avoids reconnect thundering herds.
    """
    return policy.base_delay(attempt) * rand
