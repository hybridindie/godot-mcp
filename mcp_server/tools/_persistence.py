"""Builders for the ``cmd_node_persistence`` dry-run probes (issue #476).

Every Tier 1/2 mutation that previews a persistence verdict sends the addon the same
probe its real run would key on; the addon answers ``persisted``/``reason``/``hint``.
These helpers are the single source of truth for that probe so the addon's answer is
predictable before the change is applied — and the live e2e sends the very same probe.

A probe of ``True`` marks a file-only resource author: the tool just wrote a new
``.tres`` the editor owns, so a preview reports ``persisted=True`` without a round trip.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: ``cmd_node_persistence`` params, or ``True`` (file-only resource author).
PersistenceProbe = dict[str, Any] | bool


def node_probe(node_path: str, resource_properties: Iterable[str] = ()) -> dict[str, Any]:
    """Probe the verdict for a node, optionally keying on the first Resource-typed
    property (e.g. ``tile_set``, ``mesh_library``, ``tree_root``, ``process_material``)
    the real handler would follow."""
    probe: dict[str, Any] = {"node_path": node_path}
    if resource_properties:
        probe["resource_properties"] = list(resource_properties)
    return probe


def animation_probe(node_path: str, animation: str) -> dict[str, Any]:
    """Probe an AnimationPlayer library chain: ``[animation, library]`` — the one slot a
    property lookup cannot express."""
    return {"node_path": node_path, "animation": animation}