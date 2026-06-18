"""Composite/macro tools (issue #154).

Each tool collapses a multi-step scene-edit workflow into ONE bridge round-trip
that the addon executes as a single ``UndoRedo`` action — fewer LLM turns, less
latency, and one atomic undo. They are opt-in (gated under the ``composite``
toolset); the individual ``scene_edit`` tools still work unchanged.

Thin wrappers per .claude/rules/architecture.md: validate/preconditions, route
to the addon ``cmd_*`` handler, return a typed model.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import COMPOSITE_TAG
from mcp_server.models.composite import (
    ApplyNodeEditsResult,
    BatchCreateNodesResult,
    ComposeNodeResult,
)
from mcp_server.models.run_commands import RunCommandsResult
from mcp_server.safety import (
    MUTATING,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_node_exists,
)
from mcp_server.tools._route import run_or_preview

COMPOSITE = {COMPOSITE_TAG}


def _normalize_command(command: str) -> str:
    """Accept either the addon command (``cmd_set_node_property``) or the bare
    tool name (``set_node_property``); the addon dispatches on the ``cmd_`` form."""
    return command if command.startswith("cmd_") else f"cmd_{command}"


def _child_to_addon(child: dict[str, Any]) -> dict[str, Any]:
    """Map a caller child spec to the addon's shape (``node_name`` -> ``name``).

    Uses ``.get`` for every key: a missing ``node_type`` passes "" through to the
    addon, which returns a structured ``VALIDATION_ERROR`` rather than a KeyError
    surfacing as an opaque internal failure.
    """
    return {
        "node_type": child.get("node_type", ""),
        "name": child.get("node_name") or child.get("name", ""),
        "properties": child.get("properties", {}),
    }


def register_composite(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the composite/macro tools (gated under the ``composite`` toolset)."""

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def compose_node(
        parent_path: str,
        node_type: str,
        node_name: str,
        properties: dict[str, Any] | None = None,
        script_path: str | None = None,
        children: list[dict[str, Any]] | None = None,
        save: bool = False,
        dry_run: bool = False,
    ) -> ComposeNodeResult:
        """Create a fully-configured node in one atomic step: a ``node_type`` named
        ``node_name`` under ``parent_path`` ("." is the root), with ``properties``
        set, an optional ``script_path`` (``res://``) attached, and optional
        ``children`` (each ``{node_type, node_name, properties?}``). ``save=True``
        also saves the scene. Replaces create_node + set_node_property(s) +
        attach_script + child creation — one UndoRedo action, one round-trip.
        """
        await require_active_scene(bridge)
        await require_node_exists(bridge, parent_path)
        params: dict[str, Any] = {
            "parent_path": parent_path,
            "node_type": node_type,
            "name": node_name,
            "properties": properties or {},
            "script_path": script_path or "",
            "children": [_child_to_addon(c) for c in (children or [])],
            "save": save,
        }
        node_path = node_name if parent_path in (".", "") else f"{parent_path}/{node_name}"
        preview = {
            "node_path": node_path,
            "created": False,
            "children": [c.get("node_name") or c.get("name", "") for c in (children or [])],
            "script_attached": bool(script_path),
            "properties_set": list((properties or {}).keys()),
            "saved": False,
        }
        return await run_or_preview(
            dry_run, ComposeNodeResult, preview, bridge, "cmd_compose_node", params
        )

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def batch_create_nodes(
        parent_path: str,
        node_type: str,
        names: list[str],
        properties: dict[str, Any] | None = None,
        save: bool = False,
        dry_run: bool = False,
    ) -> BatchCreateNodesResult:
        """Create many ``node_type`` nodes named by ``names`` under ``parent_path``,
        each with the same ``properties`` — one UndoRedo action, one round-trip.
        ``save=True`` also saves the scene.
        """
        await require_active_scene(bridge)
        await require_node_exists(bridge, parent_path)
        params: dict[str, Any] = {
            "parent_path": parent_path,
            "node_type": node_type,
            "names": names,
            "properties": properties or {},
            "save": save,
        }
        preview = {"created": [], "count": 0, "saved": False}
        return await run_or_preview(
            dry_run, BatchCreateNodesResult, preview, bridge, "cmd_batch_create_nodes", params
        )

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def apply_node_edits(
        edits: list[dict[str, Any]],
        save: bool = False,
        dry_run: bool = False,
    ) -> ApplyNodeEditsResult:
        """Apply per-node property edits across existing nodes in one UndoRedo
        action. ``edits`` is a list of ``{node_path, properties}``; nodes missing a
        property are reported under ``skipped``. ``save=True`` also saves the scene.
        """
        await require_active_scene(bridge)
        params: dict[str, Any] = {"edits": edits, "save": save}
        preview = {"edited": [], "skipped": [], "count": 0, "saved": False}
        return await run_or_preview(
            dry_run, ApplyNodeEditsResult, preview, bridge, "cmd_apply_node_edits", params
        )

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def run_commands(
        commands: list[dict[str, Any]],
        stop_on_error: bool = True,
        dry_run: bool = False,
    ) -> RunCommandsResult:
        """Execute a sequence of bridge commands in ONE round-trip (the addon runs
        them in a single editor frame). The editor drains commands serially —
        ~one frame of latency each — so batching N independent commands here is
        the main throughput lever for scripted harnesses.

        ``commands`` is a list of ``{command, params}``; ``command`` may be the
        bare tool name (``set_node_property``) or the addon form
        (``cmd_set_node_property``). Each sub-mutation still wraps its own
        UndoRedo action. Returns one envelope per command under ``results``;
        ``ok_all`` is True only if every command succeeded. With
        ``stop_on_error=True`` (default) the batch halts at the first failure;
        set it False to run them all. Read-only and mutating commands may be
        mixed, but order is preserved — do not rely on it for unordered writes.
        """
        require_bridge_connected(bridge)
        normalized = [
            {
                "command": _normalize_command(str(c.get("command", ""))),
                "params": c.get("params", {}),
            }
            for c in commands
        ]
        params: dict[str, Any] = {"commands": normalized, "stop_on_error": stop_on_error}
        preview = {
            "results": [],
            "ok_all": True,
            "count": len(normalized),
            "planned": [c["command"] for c in normalized],
        }
        return await run_or_preview(
            dry_run, RunCommandsResult, preview, bridge, "cmd_run_commands", params
        )
