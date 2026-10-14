"""Res:// path containment types for tool inputs (issue #637).

``res://`` paths reach Godot's ``ResourceSaver``/file APIs, and the addon's own
check is only ``begins_with("res://")`` — which accepts ``res://../x.gd`` and
``res:///etc/x``. These annotated types move the containment rule to the server
(schema level), so every file-path parameter rejects an escape or an absolute
filesystem path *before* the bridge round-trip.

Node paths (``Player/Gun``) are **not** ``res://`` paths and must not use these
types — they are exempt in the enumerating contract test.
"""

from __future__ import annotations

import posixpath
from typing import Annotated

from pydantic import AfterValidator

RES_SCHEME = "res://"


def escapes_res_root(path: str) -> bool:
    """True when a ``res://`` path escapes the project root (path traversal).

    Strips the scheme and normalizes: a result that climbs above root (``..``) or
    is absolute (``res:///etc/...``) escapes. ``res://a/../b.gd`` stays inside and
    is fine. This is the single containment predicate shared by the annotated
    types and the ``_route`` preflight validators (#205, #217, #637).
    """
    norm = posixpath.normpath(path[len(RES_SCHEME) :])
    return norm == ".." or norm.startswith("../") or posixpath.isabs(norm)


def ensure_res_path(value: str) -> str:
    """Validate a file path is a contained ``res://`` path; return it unchanged.

    Raises ``ValueError`` (surfaced by Pydantic as a param-validation error) when
    the value lacks the ``res://`` scheme or escapes the project root. An empty
    string is allowed — several tools use ``""`` to mean "not specified" (e.g.
    ``add_audio_player`` with no stream, ``create_theme`` without saving) — and
    carries no traversal risk. The path is returned verbatim (a harmless
    ``a/../b`` is not collapsed).
    """
    if value == "":
        return value
    if not value.startswith(RES_SCHEME):
        raise ValueError(
            f"must be a 'res://' path (e.g. 'res://scenes/main.tscn'); "
            f"absolute filesystem paths are not allowed (got '{value}')"
        )
    if escapes_res_root(value):
        raise ValueError(
            f"must stay inside the project ('res://'); '{value}' escapes the project root"
        )
    return value


def ensure_export_path(value: str) -> str:
    """Validate an export output path; return it unchanged.

    Exports legitimately target absolute/relative filesystem paths (often outside
    the project), so this only rejects an empty value or a NUL byte. Containment
    against the project dir (with an explicit ``confirm`` escape hatch) is
    enforced at run time in ``export_project``, where the project dir is known.
    """
    if not value or not value.strip():
        raise ValueError("output_path must not be empty")
    if "\x00" in value:
        raise ValueError("output_path must not contain a NUL byte")
    return value


# A contained ``res://`` file/directory path (see ensure_res_path).
ResPath = Annotated[str, AfterValidator(ensure_res_path)]
# An export output path (see ensure_export_path).
ExportPath = Annotated[str, AfterValidator(ensure_export_path)]

__all__ = ["ExportPath", "ResPath", "ensure_export_path", "ensure_res_path", "escapes_res_root"]
