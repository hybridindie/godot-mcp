"""Argument-completion handler (``@mcp.completion``) — issue #314.

A single server-level completion handler answers ``completion/complete`` requests
for the path-bearing prompt arguments in this server's prompts. It advertises
the completions capability at negotiation (FastMCP declares it once a handler
is registered) and returns candidate ``res://`` / scene-relative paths filtered
by the partial value the agent typed.

The handler is bridge-gated: when no editor is connected it returns no
candidates rather than crashing — the same fallback shape as the
``read_resource`` tool (resources/context.py:103-114). Each path type routes to
the cheapest addon command that can enumerate it; if a command fails the
handler returns no candidates for that argument (an unhandled completion is
empty, never an error).
"""

from __future__ import annotations

from typing import Any

import mcp_types
from fastmcp import FastMCP

from mcp_server.bridge import Bridge

# Prompt arguments that carry each kind of Godot path. Keep this table the
# single source of truth for which arguments get completed — adding a new
# path-bearing prompt argument means adding the name here, not a new handler.
_SCENE_PATH_ARGS = frozenset({"scene_path"})
_NODE_PATH_ARGS = frozenset({"node_path"})
_SCRIPT_PATH_ARGS = frozenset({"script_path"})
_RESOURCE_PATH_ARGS = frozenset({"resource_path", "save_path"})

# Bridge commands the handler queries. Kept here so the handler stays a thin
# router: a single bridge round-trip per completion request.
_LIST_SCENES = "cmd_list_scenes"
_GET_SCENE_TREE = "cmd_get_scene_tree"
_LIST_SCRIPTS = "cmd_list_scripts"
_SEARCH_FILES = "cmd_search_files"

# A generous cap below the MCP limit (100) — completion candidates are meant to
# be a short pick-list, not an exhaustive dump. The handler filters by prefix
# before applying the cap, so the cap only bites on pathologically huge trees.
_MAX_CANDIDATES = 50


def _filter(values: list[str], partial: str) -> list[str]:
    """Return the values that start with ``partial``, capped to ``_MAX_CANDIDATES``."""
    matches = [v for v in values if v.startswith(partial)]
    return matches[:_MAX_CANDIDATES]


async def _scene_paths(bridge: Bridge, partial: str) -> list[str]:
    """Enumerate project scene paths via ``cmd_list_scenes`` and filter by prefix."""
    response = await bridge.send(_LIST_SCENES)
    if not response.ok or not isinstance(response.result, dict):
        return []
    scenes = response.result.get("scenes")
    if not isinstance(scenes, list):
        return []
    paths: list[str] = []
    for entry in scenes:
        if isinstance(entry, dict):
            path = entry.get("path")
            if isinstance(path, str):
                paths.append(path)
    return _filter(paths, partial)


def _walk_node_paths(node: Any, out: list[str]) -> None:
    """Recursively collect scene-relative node paths (``.``, ``Player``, …)."""
    if not isinstance(node, dict):
        return
    path = node.get("path")
    if isinstance(path, str) and path:
        out.append(path)
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            _walk_node_paths(child, out)


async def _node_paths(bridge: Bridge, partial: str) -> list[str]:
    """Enumerate scene-relative node paths via ``cmd_get_scene_tree`` and filter."""
    response = await bridge.send(_GET_SCENE_TREE, {"max_depth": -1})
    if not response.ok or not isinstance(response.result, dict):
        return []
    tree = response.result.get("tree")
    paths: list[str] = []
    _walk_node_paths(tree, paths)
    return _filter(paths, partial)


async def _script_paths(bridge: Bridge, partial: str) -> list[str]:
    """Enumerate ``.gd`` paths via ``cmd_list_scripts`` and filter by prefix."""
    response = await bridge.send(_LIST_SCRIPTS, {"directory": "res://"})
    if not response.ok or not isinstance(response.result, dict):
        return []
    scripts = response.result.get("scripts")
    if not isinstance(scripts, list):
        return []
    paths: list[str] = [s for s in scripts if isinstance(s, str)]
    return _filter(paths, partial)


async def _resource_paths(bridge: Bridge, partial: str) -> list[str]:
    """Enumerate ``.tres`` resource paths via ``cmd_search_files`` and filter.

    ``cmd_search_files`` with a ``*.tres`` name glob is the cheapest addon
    command that yields resource file paths without walking a tree client-side.
    """
    response = await bridge.send(
        _SEARCH_FILES,
        {"directory": "res://", "name_glob": "*.tres", "content": "", "max_results": 200},
    )
    if not response.ok or not isinstance(response.result, dict):
        return []
    matches = response.result.get("matches")
    if not isinstance(matches, list):
        return []
    paths: list[str] = [m for m in matches if isinstance(m, str)]
    return _filter(paths, partial)


def register_completion(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the server's argument-completion handler.

    Advertising the completions capability is a side effect of registering the
    handler (FastMCP wires the low-level ``completion/complete`` handler on
    register). The handler is one of: a ``list[str]`` of candidates, ``None``
    when the argument is not a path it handles, and is async because the bridge
    is awaited inside.
    """

    @mcp.completion
    async def complete(
        ref: mcp_types.PromptReference | mcp_types.ResourceTemplateReference,
        argument: mcp_types.CompletionArgument,
        context: mcp_types.CompletionContext | None,
    ) -> list[str] | None:
        # Resource templates aren't used by this server; only prompts carry
        # path-bearing arguments.
        if not isinstance(ref, mcp_types.PromptReference):
            return None
        # Bridge-gated: no editor -> no candidates (no crash). Mirrors the
        # read_resource fallback in resources/context.py:103-114.
        if not bridge.connected:
            return None
        name = argument.name
        partial = argument.value or ""
        if name in _SCENE_PATH_ARGS:
            return await _scene_paths(bridge, partial)
        if name in _NODE_PATH_ARGS:
            return await _node_paths(bridge, partial)
        if name in _SCRIPT_PATH_ARGS:
            return await _script_paths(bridge, partial)
        if name in _RESOURCE_PATH_ARGS:
            return await _resource_paths(bridge, partial)
        return None