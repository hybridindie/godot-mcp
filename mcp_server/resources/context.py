"""Read-only project-context resources (issue #11).

Addressable `godot://…` snapshots so an agent can reference project/scene/node
state without a tool call each time. Resources are read-only and return JSON
strings; mutations always go through tools (see .opencode/rules/mcp-tools.md).

Only the **generic** resources are implemented here. The game-specific ones in the
issue (`godot://game/towers|enemies|waves|domain`) depend on a game's domain model
and belong to the separate game project, not this generic server.

A `read_resource(uri)` tool provides the resources-as-tools fallback for MCP
clients that don't support the resource protocol.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.output import cap_json
from mcp_server.safety import READ_ONLY

SCENE_TREE_PREFIX = "godot://scene/tree/"

# Static URI → (bridge command, params). The scene/tree depth template is handled
# separately. This is the single source of truth for both the resources and the
# read_resource fallback tool.
_STATIC: dict[str, tuple[str, dict[str, object]]] = {
    "godot://project/info": ("cmd_get_project_info", {}),
    "godot://scene/current": ("cmd_get_active_scene", {}),
    "godot://scene/tree": ("cmd_get_scene_tree", {"max_depth": -1}),
    "godot://node/selected": ("cmd_get_selected_node", {}),
}


async def _fetch_json(bridge: Bridge, command: str, params: dict[str, object]) -> str:
    """Send a command and return its result as a pretty JSON string; on failure,
    return the structured error as JSON (resources always return valid JSON)."""
    response = await bridge.send(command, params)
    if response.ok:
        # Bound large reads (e.g. a deep scene tree) so a resource can't blow up the
        # agent's context window — oversized JSON is replaced with a marker (#222).
        return cap_json(json.dumps(response.result or {}, indent=2))
    error: dict[str, object] = {"error": response.error, "hint": response.hint}
    if response.required is not None:
        error["required"] = response.required
    return json.dumps(error, indent=2)


async def _read_uri(bridge: Bridge, uri: str) -> str:
    """Resolve any supported godot:// URI to its JSON content. Raises KeyError if
    the URI is not recognized."""
    if uri in _STATIC:
        command, params = _STATIC[uri]
        return await _fetch_json(bridge, command, params)
    if uri.startswith(SCENE_TREE_PREFIX):
        tail = uri[len(SCENE_TREE_PREFIX) :]
        try:
            depth = int(tail)
        except ValueError:
            raise KeyError(uri) from None
        return await _fetch_json(bridge, "cmd_get_scene_tree", {"max_depth": depth})
    raise KeyError(uri)


def register_resources(mcp: FastMCP, bridge: Bridge) -> list[str]:
    """Register the godot:// context resources and the resources-as-tools fallback.

    Returns the registered resource URIs (the static set plus the depth template) so
    the caller can advertise them without introspecting FastMCP internals (#231/#233).
    """

    @mcp.resource("godot://project/info")
    async def project_info() -> str:
        """Project metadata: name, Godot version, main scene, autoloads, input actions."""
        return await _read_uri(bridge, "godot://project/info")

    @mcp.resource("godot://scene/current")
    async def scene_current() -> str:
        """The currently open scene: is_open, path, name (is_open=false when none)."""
        return await _read_uri(bridge, "godot://scene/current")

    @mcp.resource("godot://scene/tree")
    async def scene_tree() -> str:
        """The full active scene tree {name, type, script, children}. May be large —
        use godot://scene/tree/{max_depth} to limit depth."""
        return await _read_uri(bridge, "godot://scene/tree")

    @mcp.resource("godot://scene/tree/{max_depth}")
    async def scene_tree_depth(max_depth: int) -> str:
        """The active scene tree limited to max_depth child levels (0 = root only)."""
        return await _fetch_json(bridge, "cmd_get_scene_tree", {"max_depth": max_depth})

    @mcp.resource("godot://node/selected")
    async def node_selected() -> str:
        """The currently selected node snapshot, or {"selected": null} when none."""
        return await _read_uri(bridge, "godot://node/selected")

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def read_resource(uri: str) -> str:
        """Read a godot:// context resource by URI — the fallback for MCP clients
        without resource-protocol support. Known URIs: godot://project/info,
        godot://scene/current, godot://scene/tree, godot://scene/tree/{max_depth},
        godot://node/selected.
        """
        try:
            return await _read_uri(bridge, uri)
        except KeyError:
            known = ", ".join([*_STATIC, f"{SCENE_TREE_PREFIX}{{max_depth}}"])
            raise ToolError(f"Unknown resource URI '{uri}'. Known: {known}.") from None

    return [*_STATIC, f"{SCENE_TREE_PREFIX}{{max_depth}}"]
