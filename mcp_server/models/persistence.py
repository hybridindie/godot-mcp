"""Persistence truth for node mutation results (issue #458)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from mcp_server.models.receipt import ChangeReceipt


class PersistenceReport(BaseModel):
    """Whether a change that applied live in the editor will survive a scene save.

    ``persisted`` is ``None`` when unknown — a preview the server could not probe (issue
    #476 probes ``cmd_node_persistence`` for most previews; file-only resource authors
    and legacy previews stay ``None``). ``False`` always comes with a stable ``reason``
    token (``instanced_child_not_editable``, ``node_not_owned``,
    ``embedded_in_other_resource``, ``group_from_base_scene``) and an actionable ``hint``.

    ``receipt`` (#756) is the addon's read-back of what actually changed; it is
    orthogonal to persistence and optional while receipts are being rolled out.
    """

    persisted: bool | None = None
    reason: str | None = None
    hint: str | None = None
    receipt: ChangeReceipt | None = None
    # #760: how this change can be reversed. ``undo`` = UndoRedo-tracked;
    # ``none`` = outside the undo stack (file moves, settings, imports, etc.);
    # ``vcs`` is reserved for a VCS snapshot backstop (not shipped yet).
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


def persistence_fields(result: dict[str, Any]) -> dict[str, Any]:
    """The persistence fields of an addon result, for tools that build their model by hand
    instead of passing the whole result through."""
    return {key: result[key] for key in ("persisted", "reason", "hint") if key in result}


class TargetPersistence(BaseModel):
    """Per-target verdict inside a multi-target batch (#477).

    ``node_path`` echoes the entry the verdict describes; ``persisted``/``reason``/
    ``hint`` have the same semantics as :class:`PersistenceReport` for that one
    target. A batch result must carry one entry per applied target — an aggregate
    ``ok`` never hides a target the save will drop.
    """

    node_path: str
    persisted: bool
    reason: str | None = None
    hint: str | None = None
