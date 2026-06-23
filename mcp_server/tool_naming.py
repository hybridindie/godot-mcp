"""Uniform ``godot_`` tool naming (issue #224).

Every MCP tool is exposed as ``godot_<toolset>_<action>``, where ``<toolset>`` is the
tool's gating category (the thing you ``enable_toolset(...)`` to expose it) and
``<action>`` is its handler name with the redundant domain noun trimmed. Always-on
``core`` / meta tools are ``godot_<action>`` (they're not a Godot domain).

This gives a single, predictable convention — the name prefix *is* the toolset — which
both avoids cross-server collisions and aids agent tool selection. It is applied
centrally by :func:`install_tool_naming` (wraps ``mcp.tool`` before any tool registers),
so every current and future tool is named by construction; ``tests/contract/
test_tool_naming.py`` enforces it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from mcp_server.categories import CORE_TAG

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


def install_tool_naming(mcp: Any) -> None:
    """Wrap ``mcp.tool`` so each ``@mcp.tool(...)`` registration is exposed under its
    computed ``godot_…`` name (unless an explicit ``name=`` is already given). Call once,
    before any ``register_*``. Tools register with the final name from the start, so
    toolset gating (tag-based) and capability derivation are unaffected.
    """
    original_tool = mcp.tool

    def naming_tool(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Any]:
        def decorator(fn: Callable[..., Any]) -> Any:
            call_kwargs = dict(kwargs)
            call_kwargs.setdefault("name", godot_tool_name(fn.__name__, call_kwargs.get("tags")))
            return original_tool(*args, **call_kwargs)(fn)

        return decorator

    mcp.tool = naming_tool
