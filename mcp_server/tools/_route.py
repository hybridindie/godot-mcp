"""Bridge → tool routing helper (issue #5).

Keeps tool handlers thin (delegation only, per .claude/rules/architecture.md): send
a command, return the result dict on success, or raise a structured ``ToolError`` on
failure so the agent gets an actionable message instead of a stack trace. When the
addon returns a precondition-style envelope (carrying ``required``), that field is
included in the error text so the agent knows what to satisfy — regardless of whether
the calling tool is decorated with ``@enforce_preconditions`` (read-only tools are not).
"""

from __future__ import annotations

import asyncio
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

# Cache: {command_signature -> is_valid}
_preflight_cache: dict[str, bool] = {}

MUTATION_COMMANDS: set[str] = {
    "cmd_create_node",
    "cmd_set_node_property",
    "cmd_delete_node",
    "cmd_rename_node",
    "cmd_attach_script",
    "cmd_connect_signal",
    "cmd_write_script",
    "cmd_patch_script",
    "cmd_batch_set_property",
}


def _invalidate_preflight_cache() -> None:
    """Clear the pre-flight cache after any mutation."""
    _preflight_cache.clear()


async def _preflight_validate(
    bridge: Bridge, command: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Validate parameters before sending to Godot.

    Returns {"ok": True} if validation passes or no rules apply.
    Returns {"ok": False, "error": "...", "hint": "...", "required": "..."} on failure.
    """
    # Build a cache key from command + sorted params
    cache_key = f"{command}:{sorted(params.items())}"
    if cache_key in _preflight_cache:
        if not _preflight_cache[cache_key]:
            return {
                "ok": False,
                "error": "PARAM_ERROR",
                "hint": "Parameter validation failed (cached).",
            }
        return {"ok": True}

    # --- node_path validation ---
    # Only pre-validate existence for *mutations*. Read-only inspection commands
    # (e.g. cmd_get_node_properties) and runtime commands (e.g. cmd_monitor,
    # cmd_assert_node_state) must reach the addon so it can return its own
    # RESOURCE_NOT_FOUND/assertion envelope — pre-empting them here both masks
    # those structured errors and (for get_node_properties) recurses on itself.
    node_path = params.get("node_path", "")
    if node_path and command in MUTATION_COMMANDS and command != "cmd_create_node":
        # Skip create_node (target node doesn't exist yet — that's the point).
        try:
            resp = await bridge.send("cmd_get_node_properties", {"node_path": node_path})
            # Only a genuine "missing node" should fail preflight. Other errors
            # (e.g. PRECONDITION_FAILED for no active scene) must pass through so
            # the addon returns its own structured envelope instead of a
            # misleading "node not found".
            if not resp.ok and resp.error == "RESOURCE_NOT_FOUND":
                _preflight_cache[cache_key] = False
                return {
                    "ok": False,
                    "error": "PARAM_ERROR",
                    "hint": (
                        f"Node '{node_path}' not found in scene. "
                        "Use get_scene_tree to discover valid paths."
                    ),
                    "required": "node_path",
                }
        except Exception:
            pass  # Bridge error; fall through to addon validation

    # --- script_path validation (mutations only; cmd_read_script is read-only
    # and must reach the addon for its own envelope) ---
    _SCRIPT_MUTATIONS = {
        "cmd_attach_script",
        "cmd_write_script",
        "cmd_patch_script",
    }
    script_path = params.get("script_path", "")
    if script_path and command in _SCRIPT_MUTATIONS:
        if not script_path.startswith("res://"):
            _preflight_cache[cache_key] = False
            return {
                "ok": False,
                "error": "PARAM_ERROR",
                "hint": f"script_path must start with 'res://'. Got: '{script_path}'",
                "required": "script_path",
            }
        # File existence isn't reliably checkable server-side (project root may
        # differ); let the addon return its own RESOURCE_NOT_FOUND if missing.

    # --- parent_path validation ---
    parent_path = params.get("parent_path", "")
    if parent_path and command == "cmd_create_node":
        if parent_path not in {".", "/", ""}:
            try:
                resp = await bridge.send("cmd_get_node_properties", {"node_path": parent_path})
                if not resp.ok:
                    _preflight_cache[cache_key] = False
                    return {
                        "ok": False,
                        "error": "PARAM_ERROR",
                        "hint": f"Parent '{parent_path}' not found. Use '.' for scene root.",
                        "required": "parent_path",
                    }
            except Exception:
                pass

    # --- property validation (lightweight) ---
    prop = params.get("property", "")
    if prop and command in {"cmd_set_node_property", "cmd_batch_set_property"}:
        # We skip expensive property list checks; addon has better context
        pass

    _preflight_cache[cache_key] = True
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
    # Pre-flight validation
    validation = await _preflight_validate(bridge, command, params or {})
    if not validation.get("ok"):
        detail = f"{validation['error']}: {validation['hint']}"
        if validation.get("required"):
            detail = f"{detail} [required={validation['required']}]"
        raise ToolError(detail)

    response = await bridge.send(command, params or {})

    # Invalidate cache on mutations (scene state may have changed)
    if command in MUTATION_COMMANDS:
        _invalidate_preflight_cache()

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
