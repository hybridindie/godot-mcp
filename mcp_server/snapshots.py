"""Snapshot store for subtree snapshots (issue #535).

Snapshots are plain dicts the server owns, keyed by a stable id (``s1``, ``s2``,
…). The store is a bounded LRU: the oldest entry is evicted past ``max_entries``
so an agent taking many snapshots never grows server memory unboundedly. Pure
data plumbing — no bridge or Godot knowledge (per .opencode/rules/architecture.md).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

# Bounded default (issue #535): enough snapshot refs for a long verify-playbook
# session, capped so the store can never grow unboundedly.
MAX_ENTRIES = 32


class SnapshotStore:
    """A bounded LRU of subtree snapshots keyed by stable ids."""

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._counter = 0

    def put(self, snapshot: dict[str, Any]) -> str:
        """Store a snapshot and return its stable id (``s1``, ``s2``, …)."""
        self._counter += 1
        snapshot_id = f"s{self._counter}"
        self._entries[snapshot_id] = snapshot
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return snapshot_id

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return the snapshot for ``snapshot_id``, or None when absent/evicted."""
        snapshot = self._entries.get(snapshot_id)
        if snapshot is not None:
            self._entries.move_to_end(snapshot_id)
        return snapshot