"""Client/harness performance helpers (issue #169).

The addon drains *all* queued packets per ``_process`` frame, but a harness that
``await``s each read sequentially pays ~one frame of latency *per* read. Since the
bridge correlates responses by ``id`` (many in-flight commands resolve to their own
waiters — see ``bridge.py``), a harness can fire N independent reads concurrently and
get them all back in ~one frame instead of N.

These run in the **client/harness process** (the eval runner, a scripted client) —
they are NOT MCP tools and hold no server state, so the server's tool handlers stay
thin (see ``.claude/rules/architecture.md``). Mutations are deliberately excluded:
the editor is a single writer, so writes must stay ordered — batch those with the
``run_commands`` tool (issue #167) instead.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_server.bridge import Bridge
from mcp_server.tools._route import route

# Read-only addon commands that are safe to pipeline concurrently. A command not in
# this set is rejected by gather_reads rather than silently reordered against a write.
READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "cmd_ping",
        "cmd_get_project_info",
        "cmd_get_active_scene",
        "cmd_get_scene_tree",
        "cmd_get_selected_node",
        "cmd_get_node_properties",
        "cmd_get_node_property_list",
        "cmd_find_nodes_by_type",
        "cmd_get_dependencies",
    }
)


async def gather_reads(
    bridge: Bridge, reads: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Run independent read-only commands concurrently, returning results in order.

    ``reads`` is a list of ``(command, params)`` pairs; each ``command`` must be a
    known read-only command (see ``READ_ONLY_COMMANDS``). The reads are dispatched
    together via ``asyncio.gather`` so the addon answers them in ~one frame rather
    than one frame each — turning an O(N)-frame discovery phase into ~O(1).

    Raises ``ValueError`` if any command is not read-only (mutations must stay
    ordered — use the ``run_commands`` tool). A failing read propagates its
    ``ToolError`` (gather is not return_exceptions), so a bad path is not masked.
    """
    for command, _params in reads:
        if command not in READ_ONLY_COMMANDS:
            raise ValueError(
                f"gather_reads only pipelines read-only commands; '{command}' is not one. "
                "Mutations must stay ordered — batch them with the run_commands tool."
            )
    return list(await asyncio.gather(*(route(bridge, c, p) for c, p in reads)))
