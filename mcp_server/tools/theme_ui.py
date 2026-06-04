"""Theme & UI tools (issue #46).

Create a Theme for a Control and override theme colors, font sizes, and styleboxes on
Control nodes over the bridge. Gated `theme_ui` toolset; all `mutating` (UndoRedo-wrapped
addon-side) with `dry_run`. Overrides are local to the node and take precedence over its
assigned theme.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import THEME_UI_TAG
from mcp_server.defaults import (
    DEFAULT_STYLEBOX_TYPE,
)
from mcp_server.models.theme_ui import (
    ThemeColorResult,
    ThemeFontSizeResult,
    ThemeResult,
    ThemeStyleboxResult,
)
from mcp_server.safety import MUTATING, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route

THEME_UI = {THEME_UI_TAG}


def register_theme_ui(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the theme/UI tools."""

    @mcp.tool(meta=MUTATING, tags=THEME_UI)
    @enforce_preconditions
    async def create_theme(
        node_path: str, save_path: str = "", dry_run: bool = False
    ) -> ThemeResult:
        """Create a new Theme and assign it to the Control at ``node_path``. If
        ``save_path`` (a ``res://*.tres``) is given, the theme is also saved there as a
        shared resource; otherwise it is embedded with the scene.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ThemeResult(
                node_path=node_path, theme_path=save_path, created=False, dry_run=True
            )
        params = {"node_path": node_path, "save_path": save_path}
        return ThemeResult(**await route(bridge, "cmd_create_theme", params))

    @mcp.tool(meta=MUTATING, tags=THEME_UI)
    @enforce_preconditions
    async def set_theme_color(
        node_path: str, name: str, color: Any, dry_run: bool = False
    ) -> ThemeColorResult:
        """Override a theme color ``name`` (e.g. "font_color", "font_color_hover") on the
        Control at ``node_path``. ``color`` is an HTML string ("#ff8800") or ``[r,g,b,a]``.
        Local overrides take precedence over the node's theme.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ThemeColorResult(node_path=node_path, name=name, dry_run=True)
        params = {"node_path": node_path, "name": name, "color": color}
        return ThemeColorResult(**await route(bridge, "cmd_set_theme_color", params))

    @mcp.tool(meta=MUTATING, tags=THEME_UI)
    @enforce_preconditions
    async def set_theme_font_size(
        node_path: str, name: str, size: int, dry_run: bool = False
    ) -> ThemeFontSizeResult:
        """Override a theme font size ``name`` (e.g. "font_size") to ``size`` pixels on
        the Control at ``node_path``.
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ThemeFontSizeResult(node_path=node_path, name=name, size=size, dry_run=True)
        params = {"node_path": node_path, "name": name, "size": size}
        return ThemeFontSizeResult(**await route(bridge, "cmd_set_theme_font_size", params))

    @mcp.tool(meta=MUTATING, tags=THEME_UI)
    @enforce_preconditions
    async def set_theme_stylebox(
        node_path: str,
        name: str,
        stylebox_type: str = DEFAULT_STYLEBOX_TYPE,
        properties: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> ThemeStyleboxResult:
        """Override a theme stylebox ``name`` (e.g. "panel", "normal") on the Control at
        ``node_path`` with a new ``stylebox_type`` (StyleBoxFlat / StyleBoxTexture /
        StyleBoxEmpty / StyleBoxLine) configured with ``properties`` (e.g. ``bg_color``,
        ``corner_radius_top_left``, ``border_width_all``).
        """
        await require_node_exists(bridge, node_path)
        if dry_run:
            return ThemeStyleboxResult(
                node_path=node_path, name=name, stylebox_type=stylebox_type, dry_run=True
            )
        params = {
            "node_path": node_path,
            "name": name,
            "stylebox_type": stylebox_type,
            "properties": properties or {},
        }
        return ThemeStyleboxResult(**await route(bridge, "cmd_set_theme_stylebox", params))
