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
import posixpath
from typing import Any, TypeVar

from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from mcp_server.bridge import Bridge
from mcp_server.defaults import (
    DEFAULT_POLL_INTERVAL_SECONDS,
)

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

    Strips the scheme and normalizes: a result that climbs above root (``..``) or
    is absolute (``res:///etc/...``) escapes. ``res://a/../b.gd`` stays inside and
    is fine. Containment is enforced here (the safety layer), not in the addon.
    """
    norm = posixpath.normpath(script_path[len("res://") :])
    return norm == ".." or norm.startswith("../") or posixpath.isabs(norm)


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
    if not path.startswith("res://"):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"path must start with 'res://'. Got: '{path}'",
            "required": "path",
        }
    if _escapes_res_root(path):
        return {
            "ok": False,
            "error": "PARAM_ERROR",
            "hint": f"path escapes the project root (res://). Got: '{path}'",
            "required": "path",
        }
    return None


# Each validator returns a PARAM_ERROR dict on failure, else None. Property
# names are deliberately not validated server-side — the addon has better context.
_VALIDATORS = (_validate_script_path, _validate_delete_resource_path)


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
) -> T:
    """Return ``result_cls(**preview, dry_run=True)`` when ``dry_run`` is set,
    otherwise ``result_cls(**await route(...))``.

    Keeps tool handlers DRY: a single call replaces the
    ``if dry_run: return ...`` / ``return ... route(...)`` two-branch boilerplate.
    """
    if dry_run:
        return result_cls(**preview, dry_run=True)
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
        detail = f"{validation['error']}: {validation['hint']}"
        if validation.get("required"):
            detail = f"{detail} [required={validation['required']}]"
        raise ToolError(detail)


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
        detail = f"{response.error}: {response.hint}" if response.hint else str(response.error)
        if response.required:
            detail = f"{detail} [required={response.required}]"
        raise ToolError(detail)
    return response.result or {}


async def poll_ready(
    bridge: Bridge, command: str, params: dict[str, Any], timeout_ms: int
) -> dict[str, Any]:
    """Poll a poll-and-cache command until its result is ``ready`` or ``timeout_ms``
    elapses (whichever first), returning the last result. Uses an event-loop deadline so
    the wall-clock bound holds even for small timeouts and accounts for round-trip time.
    Always makes at least one attempt.
    """
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    result = await route(bridge, command, params)
    while not result.get("ready"):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(DEFAULT_POLL_INTERVAL_SECONDS, remaining))
        result = await route(bridge, command, params)
    return result
