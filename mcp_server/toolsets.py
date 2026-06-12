"""Toolset gating: category tags + dynamic enable/disable (issue #26).

A large flat tool surface degrades agent tool-selection and burns context, so we
keep the *live* surface small. Every tool carries a category tag; `core` is always
on; other categories ship gated off and the agent turns them on with
`enable_toolset`. As the catalog grows toward full Godot coverage, the exposed set
stays small. Built on FastMCP's tag-based `enable`/`disable` (which emit
`tools/list_changed`).

Some toolsets require a minimum Godot version because they rely on editor APIs
added in later releases (e.g. ``input_map`` needs Godot 4.4+).
"""

from __future__ import annotations

import re

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from mcp_server.bridge import Bridge
from mcp_server.categories import (
    ANALYSIS_TAG,
    ANIMATION_TAG,
    ASSET_IMPORT_TAG,
    AUDIO_TAG,
    BATCH_TAG,
    COMPOSITE_TAG,
    CORE_TAG,
    DEBUGGER_TAG,
    EDITOR_TAG,
    EXPORT_TAG,
    INPUT_MAP_TAG,
    INPUT_TAG,
    INSPECTION_TAG,
    NAVIGATION_TAG,
    PARTICLES_TAG,
    PHYSICS_TAG,
    PROFILING_TAG,
    PROJECT_SCAFFOLD_TAG,
    PROJECT_TAG,
    RESOURCES_EDIT_TAG,
    RUNTIME_TAG,
    SCENE_3D_TAG,
    SCENE_EDIT_TAG,
    SCRIPTS_TAG,
    SHADER_TAG,
    TESTING_TAG,
    THEME_UI_TAG,
    TILEMAP_TAG,
    VISUAL_SHADER_TAG,
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
    PARTICLES_TAG: "Create/configure GPU particle systems: process material, "
    "color gradients, and VFX presets.",
    NAVIGATION_TAG: "Author navigation: regions, agents, navmesh baking, and "
    "navigation layers.",
    AUDIO_TAG: "Set up audio: stream players, audio bus layout, and bus effects.",
    TILEMAP_TAG: "Edit TileMap/TileMapLayer cells: set, fill rect, get, clear, "
    "list layers.",
    THEME_UI_TAG: "Create themes and override colors, font sizes, and styleboxes "
    "on Control nodes.",
    SHADER_TAG: "Author shaders: create/read shader files, assign ShaderMaterial, "
    "set shader parameters.",
    INPUT_MAP_TAG: "Edit the project's Input Map actions and events (add/remove/clear).",
    INPUT_TAG: "Drive a running game: synthesize key/mouse/action input and play "
    "input sequences (needs a play session + runtime probe).",
    TESTING_TAG: "Automated play-testing: run scenarios, assert live node state, "
    "diff screenshots, and fuzz with random input.",
    PROFILING_TAG: "Read Godot performance monitors (FPS, draw calls, memory, "
    "physics) for the editor or a running game.",
    BATCH_TAG: "Operate over many nodes/scenes: find by type, batch-set a property, "
    "cross-scene edits, and dependency analysis.",
    ANALYSIS_TAG: "Static project analysis: unused resources, signal flow, circular "
    "script dependencies, and scene-complexity stats.",
    EXPORT_TAG: "Drive the export pipeline: list presets, report export info, and run "
    "an export (needs export templates).",
    DEBUGGER_TAG: "Debugger breakpoint control: set, remove, clear breakpoints and force "
    "breaks in a running game (needs a play session).",
    ASSET_IMPORT_TAG: "Import external assets (local files or URLs) into the project and "
    "assemble PBR materials from textures.",
    VISUAL_SHADER_TAG: "Create and edit Visual Shader node graphs: create shaders, add "
    "nodes, wire connections, and set node parameters.",
    PROJECT_SCAFFOLD_TAG: "Generate a project skeleton (directories, settings, autoloads, "
    "root scene) for common game types so agents start from a known structure.",
    COMPOSITE_TAG: "Macro tools that collapse multi-step scene edits into one atomic, "
    "single-undo round-trip (compose a node with script/children, batch-create nodes, "
    "apply many edits at once). Individual scene_edit tools still work.",
}

# Minimum Godot version (major, minor) per toolset. Categories omitted here work
# on every supported version (currently 4.4+).
TOOLSET_MIN_GODOT: dict[str, tuple[int, int]] = {
    # scene_edit contains scene_session (#79) and instance_scene (#80).
    # EditorInterface.open_scene_from_path / reload_scene_from_path /
    # save_all_scenes / select_nodes exist since 4.2, and PackedScene.instantiate()
    # (replacing instance()) is 4.0+. So scene_edit itself is broadly compatible.
    # We gate at 4.4 because the addon is only tested/validated against 4.4+.
    SCENE_EDIT_TAG: (4, 4),
    # input_map (#81) edits ProjectSettings input/ entries at runtime.
    # ProjectSettings.set_setting / save / has_setting exist in 4.2+,
    # but we test on 4.4+. Same rationale as scene_edit.
    INPUT_MAP_TAG: (4, 4),
    # TileSet authoring (#82) uses TileSetSource/AtlasSource APIs that changed
    # significantly in 4.2+. We only validate against 4.4+.
    TILEMAP_TAG: (4, 4),
    # MeshLibrary authoring (#83) creates MeshLibrary resources via the
    # ResourceSaver API; stable from 4.2+ but validated on 4.4+.
    SCENE_3D_TAG: (4, 4),
    # Everything else (inspection, scripts, resources, project, physics,
    # animation, audio, theme, shader, input_sim, runtime, testing, profiling,
    # batch, analysis, export, editor) either uses very stable APIs or has been
    # present since 4.2+. We leave them un-gated so the agent can try them;
    # the addon will produce a structured error if an API is missing.
}

# Enabled at startup (plus `core`, which is always on). Everything else is gated
# off until the agent enables it — keeping the default surface small and read-only.
DEFAULT_ENABLED: frozenset[str] = frozenset({INSPECTION_TAG})


class ToolsetInfo(BaseModel):
    """One toolset's current exposure state."""

    name: str
    enabled: bool
    description: str
    min_godot: str | None = None  # Minimum Godot version required, or None if un-gated.


class ToolsetManager:
    """Tracks which toolsets are exposed and drives FastMCP's tag enable/disable.

    One per server (long-lived, not per-request). For a single stdio client this is
    simple session state; under shared HTTP it would be process-wide (acceptable in
    v1 — documented).
    """

    def __init__(
        self,
        mcp: FastMCP,
        bridge: Bridge | None = None,
        default_enabled: frozenset[str] = DEFAULT_ENABLED,
    ) -> None:
        self._mcp = mcp
        self._bridge = bridge
        self._enabled: set[str] = {CORE_TAG} | set(default_enabled)
        self._godot_version: tuple[int, int] | None = None

    def apply_defaults(self) -> None:
        """Set the initial exposure: enable defaults, gate the rest off.

        Call once after all tools are registered.
        """
        for category in TOOLSETS:
            if category in self._enabled:
                self._mcp.enable(tags={category})
            else:
                self._mcp.disable(tags={category})

    async def enable(self, category: str) -> ToolsetInfo:
        self._check_toggleable(category)
        await self._require_godot_version(category)
        self._enabled.add(category)
        self._mcp.enable(tags={category})
        return self._info(category)

    async def disable(self, category: str) -> ToolsetInfo:
        self._check_toggleable(category)
        self._enabled.discard(category)
        self._mcp.disable(tags={category})
        return self._info(category)

    def status(self) -> list[ToolsetInfo]:
        core = ToolsetInfo(
            name=CORE_TAG,
            enabled=True,
            description="Always-on diagnostics and toolset management.",
            min_godot=None,
        )
        return [core, *(self._info(c) for c in TOOLSETS)]

    def _info(self, category: str) -> ToolsetInfo:
        req = TOOLSET_MIN_GODOT.get(category)
        return ToolsetInfo(
            name=category,
            enabled=category in self._enabled,
            description=TOOLSETS[category],
            min_godot=f"{req[0]}.{req[1]}" if req else None,
        )

    def _check_toggleable(self, category: str) -> None:
        if category == CORE_TAG:
            raise ToolError("The 'core' toolset is always enabled and cannot be toggled.")
        if category not in TOOLSETS:
            known = ", ".join(TOOLSETS)
            raise ToolError(f"Unknown toolset '{category}'. Available: {known}.")

    async def _require_godot_version(self, category: str) -> None:
        """Fail enable() if the connected Godot editor is older than the toolset's
        minimum supported version. The version is lazily queried from the bridge
        once and cached.
        """
        req = TOOLSET_MIN_GODOT.get(category)
        if req is None:
            return
        if self._bridge is None or not self._bridge.connected:
            raise ToolError(
                f"BRIDGE_DISCONNECTED: Toolset '{category}' requires Godot {req[0]}.{req[1]}+, "
                "but the Godot bridge is not connected. Start the editor with the addon "
                "enabled and retry. [required=bridge_connected]"
            )
        if self._godot_version is None:
            self._godot_version = await self._fetch_godot_version()
        if self._godot_version is None:
            raise ToolError(
                f"PRECONDITION_FAILED: Toolset '{category}' requires Godot {req[0]}.{req[1]}+, "
                "but the Godot version could not be determined. Check the editor and addon "
                "status, then retry. [required=bridge_connected]"
            )
        if self._godot_version < req:
            raise ToolError(
                f"PRECONDITION_FAILED: Toolset '{category}' requires Godot "
                f"{req[0]}.{req[1]}+ (connected editor is "
                f"{self._godot_version[0]}.{self._godot_version[1]}). "
                "Upgrade the editor or enable a different toolset. "
                "[required=godot_version]"
            )

    async def _fetch_godot_version(self) -> tuple[int, int] | None:
        """Query the addon for Godot version info and parse (major, minor).

        Returns ``None`` when the bridge call fails or the version string is
        unparseable (e.g. empty, missing, or not starting with ``MAJOR.MINOR``).
        """
        bridge = self._bridge
        if bridge is None:
            raise RuntimeError("_fetch_godot_version called with no bridge")
        try:
            # Best-effort: use a short timeout so a slow bridge doesn't hang
            # enable_toolset indefinitely.
            response = await bridge.send("cmd_get_project_info", timeout=3.0)
        except Exception:
            return None
        if not response.ok:
            return None
        version_str = (response.result or {}).get("godot_version", "")
        return _parse_godot_version(version_str)


def _parse_godot_version(version_str: str) -> tuple[int, int] | None:
    """Parse a Godot version string (e.g. ``"4.4.1-stable"``) into ``(major, minor)``.

    Returns ``None`` if the string does not **start** with a ``MAJOR.MINOR`` pattern.
    """
    if not version_str:
        return None
    m = re.match(r"(\d+)\.(\d+)", version_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


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
        return await manager.enable(category)

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def disable_toolset(category: str) -> ToolsetInfo:
        """Hide a toolset's tools again to keep the active tool surface small."""
        return await manager.disable(category)
