"""Bridge → tool routing helper (issue #5).

Keeps tool handlers thin (delegation only, per .opencode/rules/architecture.md): send
a command, return the result dict on success, or raise a structured ``ToolError`` on
failure so the agent gets an actionable message instead of a stack trace. When the
addon returns a precondition-style envelope (carrying ``required``), that field is
included in the error text so the agent knows what to satisfy.

Convention for ``@enforce_preconditions``: apply it to any tool that can raise
``PreconditionError`` before calling ``route()`` (e.g. via ``require_godot_binary``,
``require_bridge_connected``, ``require_active_scene``, ``require_node_exists``).
Read-only tools that never raise ``PreconditionError`` don't need it; ``route()``
already shapes addon-side precondition envelopes into ``ToolError``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from mcp_server.agent_errors import AgentToolError
from mcp_server.bridge import Bridge
from mcp_server.defaults import (
    DEFAULT_POLL_INTERVAL_SECONDS,
)
from mcp_server.paths import escapes_res_root

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------
#
# Pre-flight does **pure-string** parameter checks only. It deliberately does NOT
# round-trip the bridge to confirm a node/parent exists (#166): every mutating MCP
# tool already enforces that via require_node_exists / require_active_scene
# (mcp_server/safety.py), and the LLM eval bypasses route() entirely — so a
# preflight existence probe was a wasted ~70ms round-trip per mutation with no
# unique value. Likewise there is no module-level cache (the old one was global
# mutable state that bled across sessions and self-cleared on every mutation).

# Script-writing mutations; read-only cmd_read_script is excluded so it reaches
# the addon for its own envelope.
_SCRIPT_MUTATIONS: set[str] = {
    "cmd_attach_script",
    "cmd_write_script",
    "cmd_patch_script",
}


def _escapes_res_root(script_path: str) -> bool:
    """True when a ``res://`` path escapes the project root (path traversal).

    Delegates to :func:`mcp_server.paths.escapes_res_root` — the single
    containment predicate shared with the ``ResPath`` annotated type (#637).
    ``res://a/../b.gd`` stays inside and is fine; containment is enforced in the
    safety layer, not the addon.
    """
    return escapes_res_root(script_path)


async def _validate_script_path(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Fail a script mutation whose path isn't a contained ``res://`` path.

    File existence isn't reliably checkable server-side (project root may differ);
    the addon returns its own RESOURCE_NOT_FOUND if the file is missing.
    """
    script_path = params.get("script_path", "")
    if not (script_path and command in _SCRIPT_MUTATIONS):
        return None
    if not script_path.startswith("res://"):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"script_path must start with 'res://'. Got: '{script_path}'",
            "required": "script_path",
        }
    if _escapes_res_root(script_path):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"script_path escapes the project root (res://). Got: '{script_path}'",
            "required": "script_path",
        }
    return None


async def _validate_delete_resource_path(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Fail a resource-file deletion whose ``path`` isn't a contained ``res://`` path
    (issue #217) — mirrors the script-write containment hardening (#205)."""
    if command != "cmd_delete_resource_file":
        return None
    path = params.get("path", "")
    return _containment_failure(path, "path")


def _containment_failure(path: str, field: str) -> dict[str, Any] | None:
    """A ``PARAM_ERROR`` dict when ``path`` isn't a contained ``res://`` path, else None."""
    if not path.startswith("res://"):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"{field} must start with 'res://'. Got: '{path}'",
            "required": field,
        }
    if _escapes_res_root(path):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"{field} escapes the project root (res://). Got: '{path}'",
            "required": field,
        }
    return None


async def _validate_move_resource_file(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Fail a file move whose endpoints aren't contained ``res://`` paths (#532)."""
    if command != "cmd_move_resource_file":
        return None
    return _containment_failure(params.get("path", ""), "path") or _containment_failure(
        params.get("new_path", ""), "new_path"
    )


# File-authoring commands and their ``res://`` path params (issue #637). A direct
# tool call already enforces containment via the ``ResPath`` annotated type; this
# table covers ``run_commands`` sub-commands, which bypass the tool argument
# schema and would otherwise reach the addon's ``begins_with("res://")`` check
# (which accepts ``res://../x`` and ``res:///etc``).
_RES_CONTAINED_PARAMS: dict[str, tuple[str, ...]] = {
    "cmd_create_resource": ("resource_path",),
    "cmd_set_resource_property": ("resource_path",),
    "cmd_register_autoload": ("path",),
    "cmd_create_shader": ("shader_path",),
    "cmd_assign_shader_material": ("shader_path",),
    "cmd_create_visual_shader": ("path",),
    "cmd_add_shader_node": ("shader_path",),
    "cmd_connect_shader_nodes": ("shader_path",),
    "cmd_set_shader_node_param": ("shader_path",),
    "cmd_create_scene": ("scene_path",),
    "cmd_instance_scene": ("scene_path",),
    "cmd_extract_scene": ("scene_path",),
    "cmd_create_theme": ("save_path",),
    "cmd_create_tileset": ("save_path",),
    "cmd_add_tileset_atlas_source": ("texture_path", "tileset_path"),
    "cmd_create_tile": ("tileset_path",),
    "cmd_create_mesh_library": ("save_path",),
    "cmd_add_mesh_library_item": ("library_path", "mesh_path"),
    "cmd_import_asset": ("target_path",),
    "cmd_create_material_from_textures": ("path",),
}


async def _validate_res_contained(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Fail a file-authoring command whose ``res://`` path param escapes (issue #637).

    Empty values are skipped (``""`` means "not specified" for several commands).
    """
    for field in _RES_CONTAINED_PARAMS.get(command, ()):
        value = params.get(field, "")
        if isinstance(value, str) and value:
            failure = _containment_failure(value, field)
            if failure is not None:
                return failure
    return None


# Each validator returns a PARAM_ERROR dict on failure, else None. Property
# names are deliberately not validated server-side — the addon has better context.
_VALIDATORS = (
    _validate_script_path,
    _validate_delete_resource_path,
    _validate_move_resource_file,
    _validate_res_contained,
)


async def _preflight_validate(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Validate parameters before sending to Godot, running each rule in turn.

    Returns {"ok": True} if validation passes or no rules apply.
    Returns {"ok": False, "error": "...", "hint": "...", "required": "..."} on the
    first failure. Pure-string checks only — no bridge round-trips, no cache (#166).
    """
    for validate in _VALIDATORS:
        failure = await validate(bridge, command, params)
        if failure is not None:
            return failure
    return {"ok": True}


async def run_or_preview(
    dry_run: bool,
    result_cls: type[T],
    preview: dict[str, Any],
    bridge: Bridge,
    command: str,
    params: dict[str, Any] | None = None,
    persistence_probe: dict[str, Any] | bool | None = None,
) -> T:
    """Return ``result_cls(**preview, dry_run=True)`` when ``dry_run`` is set,
    otherwise ``result_cls(**await route(...))``.

    Keeps tool handlers DRY: a single call replaces the
    ``if dry_run: return ...`` / ``return ... route(...)`` two-branch boilerplate.

    ``persistence_probe`` is consulted on dry-run only (issue #476): a preview must
    predict the real run's ``persisted``/``reason``/``hint`` instead of silently
    leaving them unset. ``False``/``None`` (default) stamps nothing; ``True`` means the
    edit is already on disk (a file-only resource author), so ``persisted=True``;
    a dict is sent as the ``cmd_node_persistence`` probe params and its verdict is
    stamped into the preview.
    """
    if dry_run:
        fields = dict(preview)
        if persistence_probe is True:
            fields["persisted"] = True
        elif isinstance(persistence_probe, dict):
            truth = await route(bridge, "cmd_node_persistence", persistence_probe)
            fields["persisted"] = truth.get("persisted")
            fields["reason"] = truth.get("reason")
            fields["hint"] = truth.get("hint")
        return result_cls(**fields, dry_run=True)
    return result_cls(**await route(bridge, command, params or {}))


async def validate_or_raise(
    bridge: Bridge, command: str, params: dict[str, Any] | None = None
) -> None:
    """Run pre-flight validation; raise a structured ``ToolError`` on failure.

    Exposed so callers that *don't* go through ``route`` (e.g. ``write_script``'s
    dry-run existence probe) still enforce the same param checks — a dry-run must
    not be a containment bypass (#205).
    """
    validation = await _preflight_validate(bridge, command, params or {})
    if not validation.get("ok"):
        raise AgentToolError(
            str(validation["error"]),
            str(validation["hint"]),
            required=validation.get("required"),
            next_call=validation.get("next_call"),
        )


async def route(
    bridge: Bridge, command: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send a command over the bridge; return its result or raise a structured error.

    Pre-flight validation runs first to catch bad params before they hit Godot.
    On failure raises a ``ToolError`` of the form ``"<error>: <hint> [required=<x>]"``
    (the ``[required=...]`` suffix only when the envelope carries one), matching the
    shape ``PreconditionError.as_tool_error()`` produces — so a precondition surfaced
    by the addon is actionable even from an undecorated read-only tool.
    """
    await validate_or_raise(bridge, command, params)

    response = await bridge.send(command, params or {})

    if not response.ok:
        raise AgentToolError(
            response.error or "INTERNAL_ERROR",
            response.hint or "",
            required=response.required,
            next_call=response.next_call,
        )
    return response.result or {}


async def poll_ready(
    bridge: Bridge,
    command: str,
    params: dict[str, Any],
    timeout_ms: int,
    *,
    terminal: Callable[[dict[str, Any]], bool] | None = None,
    raise_on_timeout: bool = True,
) -> dict[str, Any]:
    """Poll a poll-and-cache command until ``terminal(result)`` or ``timeout_ms``
    elapses (whichever first), returning the last result. Uses an event-loop deadline
    so the wall-clock bound holds even for small timeouts and accounts for round-trip
    time. Always makes at least one attempt.

    ``terminal`` defaults to ``result["ready"]``; a soft read that reports state
    rather than refusing (e.g. the live scene tree, which is ``ready`` only once its
    request-scoped reply lands but is also terminal when probe-disconnected) passes
    its own predicate.

    #459: a poll that never becomes ready is a structured failure, not a bare
    ``{ready: false}`` — when the last result carries a ``reason`` token (the
    addon self-reports why it is pending), the expiry raises a ``TIMEOUT`` ToolError
    relaying it, so the agent can act on the cause instead of guessing. A soft read
    passes ``raise_on_timeout=False`` to get the pending state back instead.
    """
    is_done = terminal if terminal is not None else (lambda r: bool(r.get("ready")))
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    result = await route(bridge, command, params)
    while not is_done(result):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            reason = result.get("reason")
            if raise_on_timeout and reason:
                raise ToolError(
                    f"TIMEOUT: {command} did not become ready within {timeout_ms}ms "
                    f"(last reason: {reason}). {result.get('hint', '')}".rstrip()
                )
            break
        await asyncio.sleep(min(DEFAULT_POLL_INTERVAL_SECONDS, remaining))
        result = await route(bridge, command, params)
    return result
