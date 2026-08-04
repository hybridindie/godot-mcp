"""Declarative ``godot_`` tool naming via FastMCP 4.0's ``ToolTransform`` (issue #312).

Replaces the ``install_tool_naming`` monkeypatch that wrapped ``mcp.tool`` before
any registration. ``ToolTransform`` renames tools as they flow from providers to
clients — its built-in reverse map routes ``call_tool("godot_…")`` back to the
original handler. The naming logic (``godot_tool_name``) is unchanged from
issue #224; it now lives here, the only module that needs it.

The rename map is built eagerly after every ``register_*`` call so the
transform can reverse-map public names to original handler names without a
list-scan on every ``call_tool``. Tools are registered once at server build
time (in ``create_server``), so the map is complete before the transform is
installed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from fastmcp.server.transforms import ToolTransform
from fastmcp.tools.tool_transform import ToolTransformConfig

from mcp_server.categories import CORE_TAG

if TYPE_CHECKING:
    from fastmcp.tools.base import Tool

PREFIX = "godot_"

# Single-noun toolsets: strip these redundant tokens from the action, since the toolset
# prefix already carries the domain (e.g. audio's ``add_audio_bus`` -> ``add_bus``).
_TRIM: dict[str, set[str]] = {
    "audio": {"audio"},
    "animation": {"animation"},
    "particles": {"particle", "particles"},
    "navigation": {"navigation"},
    "theme_ui": {"theme"},
    "shader": {"shader"},
    "visual_shader": {"shader", "visual"},
    "input_map": {"input"},
    "input": {"input"},
    "export": {"export"},
    "physics": {"physics"},
    "editor": {"editor"},
    "tilemap": {"tilemap"},
}

# Tools that don't trim cleanly by rule — hand-picked full exposed names.
_OVERRIDE: dict[str, str] = {
    "scaffold_project": "godot_project_scaffold",
    "import_asset": "godot_asset_import_asset",
    "get_import_status": "godot_asset_import_get_status",
    "get_script_for_node": "godot_scripts_get_for_node",
}

# scripts: trim "script" only where the result stays unambiguous.
_SCRIPT_TRIM = {
    "read_script": "read",
    "write_script": "write",
    "list_scripts": "list",
    "patch_script": "patch",
}


def _category(tags: Iterable[str] | None) -> str:
    """The tool's gating category: its single non-core tag, or ``core``."""
    non_core = sorted(t for t in (tags or ()) if t != CORE_TAG)
    return non_core[0] if non_core else CORE_TAG


def _original_handler_name(tool: Tool) -> str:
    """Resolve a tool's original handler name, walking ``TransformedTool.parent_tool``.

    ``ToolTransformConfig.apply`` wraps each renamed tool in a ``TransformedTool``
    whose ``fn`` is a forwarding closure (``__name__ == "_forward"``); the original
    handler is reachable via ``parent_tool``. Untransformed tools expose their
    handler directly on ``fn.__name__``.
    """
    name: str = getattr(tool, "fn").__name__  # noqa: B009  (FunctionTool.fn, untyped on base Tool)
    while name == "_forward" and hasattr(tool, "parent_tool"):
        tool = getattr(tool, "parent_tool")  # noqa: B009  (TransformedTool.parent_tool)
        name = getattr(tool, "fn").__name__  # noqa: B009  (FunctionTool.fn, untyped on base Tool)
    return name


def godot_tool_name(func_name: str, tags: Iterable[str] | None) -> str:
    """Compute the exposed ``godot_…`` name for a handler ``func_name`` + its category tags."""
    if func_name in _OVERRIDE:
        return _OVERRIDE[func_name]
    cat = _category(tags)
    if cat == CORE_TAG:
        return PREFIX + func_name
    if cat == "scripts" and func_name in _SCRIPT_TRIM:
        return f"{PREFIX}scripts_{_SCRIPT_TRIM[func_name]}"
    action = func_name
    if cat in _TRIM:
        toks = [t for t in func_name.split("_") if t not in _TRIM[cat]]
        action = "_".join(toks) if toks else cat.split("_")[0]
    # Avoid doubling when the action already leads with the category token.
    if action == cat or action.startswith(cat + "_"):
        return PREFIX + action
    return f"{PREFIX}{cat}_{action}"


def godot_tool_transform(mcp: Any) -> ToolTransform:
    """Build a ``ToolTransform`` exposing each tool as ``godot_<toolset>_<action>``.

    Reads the registered tools synchronously from the server's local provider
    (``create_server`` is sync, so the async ``_list_tools`` isn't available) and
    builds the rename map + its reverse in one pass. Call after every
    ``register_*`` so the map covers the whole surface.
    """
    tools = _registered_tools(mcp)
    transforms: dict[str, ToolTransformConfig] = {}
    for tool in tools:
        public = godot_tool_name(getattr(tool, "fn").__name__, tool.tags)  # noqa: B009  (FunctionTool.fn, untyped on base Tool)
        if public != tool.name:
            transforms[tool.name] = ToolTransformConfig(name=public)
    return ToolTransform(transforms)


def _registered_tools(mcp: Any) -> Sequence[Tool]:
    """Synchronously read the tools registered on the server's local provider.

    ``FastMCP._list_tools`` is async, but the local provider's component dict is
    populated synchronously by the ``register_*`` calls, so this reads it
    without an event loop. The server built by ``create_server`` has exactly one
    ``LocalProvider``; this helper is only called there, at build time.
    """
    from fastmcp.tools.base import Tool

    tools: list[Tool] = []
    for provider in mcp.providers:
        for component in provider._components.values():
            if isinstance(component, Tool):
                tools.append(component)
    return tools


__all__ = ["godot_tool_name", "godot_tool_transform"]