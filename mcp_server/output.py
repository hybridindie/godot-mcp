"""Output bounding for read tools and resources (issue #222).

Large reads (a deep scene tree) and unpaginated list operations bloat the agent's
context window. This module centralizes two guards:

* :func:`paginate` — slice a list to a ``limit``/``offset`` window and report the
  ``total``/``truncated``/``next_offset`` so the agent can page.
* :data:`CHARACTER_LIMIT` + :func:`cap_json` — replace an oversized JSON payload with
  an explicit truncation marker so the client never receives a context-blowing blob.
"""

from __future__ import annotations

import json
from typing import TypeVar

T = TypeVar("T")

# Max characters in a single read payload before it is truncated/marked.
CHARACTER_LIMIT = 25_000

# Hint shown to the agent when a read is bounded, so it knows how to narrow next time.
_NARROW_HINT = (
    "Output exceeded the character limit. Narrow the query: use a smaller max_depth "
    "(or godot://scene/tree/{max_depth}) for the scene tree, lightweight=true, or a "
    "paginated list tool (find_nodes_by_type / list_scripts) with limit/offset."
)


def paginate(items: list[T], offset: int, limit: int) -> tuple[list[T], int, bool, int | None]:
    """Return ``(window, total, truncated, next_offset)`` for ``items[offset:offset+limit]``.

    ``truncated`` is true when items remain past the window; ``next_offset`` is the
    offset to pass for the next page (``None`` when the window reaches the end).
    """
    total = len(items)
    start = max(0, min(offset, total))
    window = items[start : start + limit]
    end = start + len(window)
    truncated = end < total
    return window, total, truncated, (end if truncated else None)


def cap_json(text: str, *, limit: int = CHARACTER_LIMIT) -> str:
    """Return ``text`` unchanged, or a JSON truncation marker when it exceeds ``limit``.

    Used for resource payloads (JSON strings): truncating the string itself would
    yield invalid JSON, so an oversized payload is replaced wholesale with a marker.
    """
    if len(text) <= limit:
        return text
    return json.dumps(
        {
            "truncated": True,
            "character_limit": limit,
            "actual_length": len(text),
            "hint": _NARROW_HINT,
        },
        indent=2,
    )


def over_character_limit(text: str, *, limit: int = CHARACTER_LIMIT) -> bool:
    """True when ``text`` exceeds the character limit."""
    return len(text) > limit


TRUNCATION_HINT = _NARROW_HINT
