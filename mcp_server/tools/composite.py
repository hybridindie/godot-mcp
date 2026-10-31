"""Composite/macro tools (issue #154).

Each tool collapses a multi-step scene-edit workflow into ONE bridge round-trip
that the addon executes as a single ``UndoRedo`` action — fewer LLM turns, less
latency, and one atomic undo. They are opt-in (gated under the ``composite``
toolset); the individual ``scene_edit`` tools still work unchanged.

Thin wrappers per .claude/rules/architecture.md: validate/preconditions, route
to the addon ``cmd_*`` handler, return a typed model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import COMPOSITE_TAG
from mcp_server.models.composite import (
    ApplyNodeEditsResult,
    BatchCreateNodesResult,
    ChildSpec,
    ComposeNodeResult,
    NodeEdit,
)
from mcp_server.models.run_commands import RunCommandEntry, RunCommandsResult
from mcp_server.paths import ResPath
from mcp_server.safety import (
    MUTATING,
    enforce_preconditions,
    require_active_scene,
    require_bridge_connected,
    require_node_exists,
)
from mcp_server.subcommand_policy import guard_batch
from mcp_server.tools._persistence import node_probe
from mcp_server.tools._route import run_or_preview

if TYPE_CHECKING:
    from mcp_server.toolset_middleware import ToolsetMiddleware

COMPOSITE = {COMPOSITE_TAG}


def _normalize_command(command: str) -> str:
    """Resolve a sub-command to the addon ``cmd_*`` form (#420).

    Accepts the addon command (``cmd_set_physics_layers``), the bare handler
    name (``create_node``), or the bare *exposed* tool name including trimmed /
    reordered actions (``physics_set_layers`` -> ``cmd_set_physics_layers``,
    ``add_bus`` -> ``cmd_add_audio_bus``) via the registry-mirrored table in
    ``command_map``. Raises a structured error with a suggestion on a miss.
    """
    from mcp_server.command_map import resolve_command

    return resolve_command(command)


def _map_batch_params(command: str, params: dict[str, Any]) -> dict[str, Any]:
    """Translate a batch entry's param keys to the addon envelope keys (#421).

    Batch entries carry agent-facing tool params; the addon expects the
    canonical keys the tool layer normally maps (``node_name`` -> ``name``).
    The command string (either form) maps via the same alias table.
    """
    from mcp_server.command_map import map_params, resolve_command

    try:
        resolved = resolve_command(command)
    except Exception:
        return params  # unresolvable commands error in _normalize_command anyway
    return map_params(resolved.removeprefix("cmd_"), params)


def _child_to_addon(child: ChildSpec) -> dict[str, Any]:
    """Map a caller child spec to the addon's shape (``node_name`` -> ``name``)."""
    return {
        "node_type": child.node_type,
        "name": child.node_name,
        "properties": child.properties,
    }


def register_composite(
    mcp: FastMCP, bridge: Bridge, toolset_mw: ToolsetMiddleware
) -> None:
    """Register the composite/macro tools (gated under the ``composite`` toolset).

    ``toolset_mw`` is the server-global gating middleware: ``run_commands``
    resolves each sub-command to its toolset and refuses entries whose toolset is
    disabled, matching the surface it would have if called directly (#634).
    """

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def compose_node(
        parent_path: str,
        node_type: str,
        node_name: str,
        properties: dict[str, Any] | None = None,
        script_path: ResPath | None = None,
        children: list[ChildSpec] | None = None,
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
            "children": [c.node_name for c in (children or [])],
            "script_attached": bool(script_path),
            "properties_set": list((properties or {}).keys()),
            "saved": False,
        }
        return await run_or_preview(
            dry_run,
            ComposeNodeResult,
            preview,
            bridge,
            "cmd_compose_node",
            params,
            persistence_probe=node_probe(parent_path, probe_parent=True),
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
        preview = {"created": [], "count": 0, "saved": False, "undoable": True, "hint": ""}
        return await run_or_preview(
            dry_run,
            BatchCreateNodesResult,
            preview,
            bridge,
            "cmd_batch_create_nodes",
            params,
            persistence_probe=node_probe(parent_path, probe_parent=True),
        )

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def apply_node_edits(
        edits: list[NodeEdit],
        save: bool = False,
        dry_run: bool = False,
    ) -> ApplyNodeEditsResult:
        """Apply per-node property edits across existing nodes in one UndoRedo
        action. ``edits`` is a list of ``{node_path, properties}``; nodes missing a
        property are reported under ``skipped``. ``save=True`` also saves the scene.
        """
        await require_active_scene(bridge)
        params: dict[str, Any] = {"edits": [e.model_dump() for e in edits], "save": save}
        preview = {
            "edited": [],
            "skipped": [],
            "count": 0,
            "saved": False,
            "undoable": True,
            "hint": "",
        }
        return await run_or_preview(
            dry_run,
            ApplyNodeEditsResult,
            preview,
            bridge,
            "cmd_apply_node_edits",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=COMPOSITE)
    @enforce_preconditions
    async def run_commands(
        commands: list[RunCommandEntry],
        stop_on_error: bool = True,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> RunCommandsResult:
        """Execute a sequence of bridge commands in ONE round-trip (one editor
        frame; the editor drains serially, so batching N independent commands is the
        main throughput lever). ``commands`` is ``[{command, params}]``; ``command``
        is the bare tool name or the addon ``cmd_*`` form. Each sub-mutation wraps its
        own UndoRedo action; ``ok_all`` is true only if every command succeeded;
        ``stop_on_error`` (default true) halts at the first failure.

        Safety is per-entry, not this tool's class: a disabled-toolset entry is
        refused (enable it first), a destructive entry needs ``confirm=True``, and
        each entry's params go through the server path preflight. ``plan`` names the
        resolved tool/toolset/safety class (populated on ``dry_run`` too).
        """
        require_bridge_connected(bridge)
        normalized = [
            {
                "command": _normalize_command(c.command),
                "params": _map_batch_params(c.command, c.params),
            }
            for c in commands
        ]
        # Reject nesting up front: a run_commands inside run_commands would recurse
        # the editor's dispatch and crash it (the addon rejects it too, defensively).
        if any(c["command"] == "cmd_run_commands" for c in normalized):
            raise ToolError(
                "PARAM_ERROR: run_commands cannot be nested inside run_commands. "
                "[required=commands]"
            )
        # #634: the batch is not a safety bypass — resolve each entry to its own
        # tool and enforce its toolset gate, destructive confirm, and path preflight.
        plans = await guard_batch(
            mcp,
            bridge,
            toolset_mw.enabled(),
            normalized,
            confirm=confirm,
            dry_run=dry_run,
        )
        params: dict[str, Any] = {"commands": normalized, "stop_on_error": stop_on_error}
        preview = {
            "results": [],
            "ok_all": True,
            "count": len(normalized),
            "planned": [c["command"] for c in normalized],
            "plan": plans,
        }
        result = await run_or_preview(
            dry_run,
            RunCommandsResult,
            preview,
            bridge,
            "cmd_run_commands",
            params,
        )
        result.plan = plans
        return result
