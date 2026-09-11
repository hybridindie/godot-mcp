"""Persistence truth for node mutation results (issue #458)."""

from __future__ import annotations

from pydantic import BaseModel


class PersistenceReport(BaseModel):
    """Whether a change that applied live in the editor will survive a scene save.

    ``persisted`` is ``None`` when unknown — a ``dry_run`` preview, since only the editor
    can tell. ``False`` always comes with a stable ``reason`` token
    (``instanced_child_not_editable``, ``node_not_owned``,
    ``embedded_in_other_resource``) and an actionable ``hint``.
    """

    persisted: bool | None = None
    reason: str | None = None
    hint: str | None = None
