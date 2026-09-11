"""Persistence truth for node mutation results (issue #458)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PersistenceReport(BaseModel):
    """Whether a change that applied live in the editor will survive a scene save.

    ``persisted`` is ``None`` when unknown — a ``dry_run`` preview, since only the editor
    can tell. ``False`` always comes with a stable ``reason`` token
    (``instanced_child_not_editable``, ``node_not_owned``,
    ``embedded_in_other_resource``, ``group_from_base_scene``) and an actionable ``hint``.
    """

    persisted: bool | None = None
    reason: str | None = None
    hint: str | None = None


def persistence_fields(result: dict[str, Any]) -> dict[str, Any]:
    """The persistence fields of an addon result, for tools that build their model by hand
    instead of passing the whole result through."""
    return {key: result[key] for key in ("persisted", "reason", "hint") if key in result}
