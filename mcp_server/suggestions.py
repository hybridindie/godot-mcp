"""Property-name suggestion engine (issue #109).

Lightweight difflib-based closest-match finder for use when a property name is
misspelled or doesn't exist on a node/resource/shader. No external dependencies.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence


def suggest(
    given: str,
    candidates: Sequence[str],
    *,
    n: int = 3,
    cutoff: float = 0.5,
) -> list[str]:
    """Return the top ``n`` closest strings to ``given`` from ``candidates``.

    Uses ``difflib.get_close_matches``; ``cutoff`` is the minimum similarity
    score (0–1). Empty string yields no suggestions.
    """
    if not given or not candidates:
        return []
    return difflib.get_close_matches(given, candidates, n=n, cutoff=cutoff)

