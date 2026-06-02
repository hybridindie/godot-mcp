"""Toolset gating: category tags + dynamic enable/disable (issue #26).

A large flat tool surface degrades agent tool-selection and burns context, so we
keep the *live* surface small. Every tool carries a category tag; `core` is always
on; other categories ship gated off and the agent turns them on with
`enable_toolset`. As the catalog grows toward full Godot coverage, the exposed set
stays small. Built on FastMCP's tag-based `enable`/`disable` (which emit
`tools/list_changed`).
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from mcp_server.categories import (
    ANIMATION_TAG,
    CORE_TAG,
    EDITOR_TAG,
    INSPECTION_TAG,
    PHYSICS_TAG,
    PROJECT_TAG,
    RESOURCES_EDIT_TAG,
    RUNTIME_TAG,
    SCENE_3D_TAG,
    SCENE_EDIT_TAG,
    SCRIPTS_TAG,
)
from mcp_server.safety import READ_ONLY

# Toggleable toolsets (category → agent-facing description). `core` is not here.
TOOLSETS: dict[str, str] = {
    INSPECTION_TAG: "Read-only project, scene, and node inspection.",
    SCENE_EDIT_TAG: "Create, modify, and delete nodes, scripts, signals, and scenes "
    "(mutating + destructive).",
    RUNTIME_TAG: "Run the project headless and capture its output/errors.",
    SCRIPTS_TAG: "Read, write, and patch GDScript files; check for parse errors.",
    RESOURCES_EDIT_TAG: "Read/create/edit resource (.tres) files and register autoloads.",
    PROJECT_TAG: "Explore the filesystem, search files, read/write project settings, resolve UIDs.",
    EDITOR_TAG: "Capture editor screenshots (image content for vision-capable clients).",
    PHYSICS_TAG: "Configure physics bodies, collision shapes, layers/masks, and raycasts.",
    ANIMATION_TAG: "Author animations (tracks/keyframes) and AnimationTree "
    "state machines/blend trees.",
    SCENE_3D_TAG: "Build 3D scenes: mesh instances, cameras, lights, "
    "WorldEnvironment, and GridMap cells.",
}

# Enabled at startup (plus `core`, which is always on). Everything else is gated
# off until the agent enables it — keeping the default surface small and read-only.
DEFAULT_ENABLED: frozenset[str] = frozenset({INSPECTION_TAG})


class ToolsetInfo(BaseModel):
    """One toolset's current exposure state."""

    name: str
    enabled: bool
    description: str


class ToolsetManager:
    """Tracks which toolsets are exposed and drives FastMCP's tag enable/disable.

    One per server (long-lived, not per-request). For a single stdio client this is
    simple session state; under shared HTTP it would be process-wide (acceptable in
    v1 — documented).
    """

    def __init__(self, mcp: FastMCP, default_enabled: frozenset[str] = DEFAULT_ENABLED) -> None:
        self._mcp = mcp
        self._enabled: set[str] = {CORE_TAG} | set(default_enabled)

    def apply_defaults(self) -> None:
        """Set the initial exposure: enable defaults, gate the rest off.

        Call once after all tools are registered.
        """
        for category in TOOLSETS:
            if category in self._enabled:
                self._mcp.enable(tags={category})
            else:
                self._mcp.disable(tags={category})

    def enable(self, category: str) -> ToolsetInfo:
        self._check_toggleable(category)
        self._enabled.add(category)
        self._mcp.enable(tags={category})
        return self._info(category)

    def disable(self, category: str) -> ToolsetInfo:
        self._check_toggleable(category)
        self._enabled.discard(category)
        self._mcp.disable(tags={category})
        return self._info(category)

    def status(self) -> list[ToolsetInfo]:
        core = ToolsetInfo(
            name=CORE_TAG,
            enabled=True,
            description="Always-on diagnostics and toolset management.",
        )
        return [core, *(self._info(c) for c in TOOLSETS)]

    def _info(self, category: str) -> ToolsetInfo:
        return ToolsetInfo(
            name=category, enabled=category in self._enabled, description=TOOLSETS[category]
        )

    def _check_toggleable(self, category: str) -> None:
        if category == CORE_TAG:
            raise ToolError("The 'core' toolset is always enabled and cannot be toggled.")
        if category not in TOOLSETS:
            known = ", ".join(TOOLSETS)
            raise ToolError(f"Unknown toolset '{category}'. Available: {known}.")


def register_toolset_tools(mcp: FastMCP, manager: ToolsetManager) -> None:
    """Register the always-on toolset introspection/management tools."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def list_toolsets() -> list[ToolsetInfo]:
        """List the available toolsets (tool categories) and whether each is currently
        enabled. Enable a toolset with enable_toolset before using its tools.
        """
        return manager.status()

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def enable_toolset(category: str) -> ToolsetInfo:
        """Expose a toolset's tools (e.g. "scene_edit") for this session. Returns the
        toolset's new state. Does not change anything in the Godot project.
        """
        return manager.enable(category)

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def disable_toolset(category: str) -> ToolsetInfo:
        """Hide a toolset's tools again to keep the active tool surface small."""
        return manager.disable(category)
