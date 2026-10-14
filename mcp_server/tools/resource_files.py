"""Resource-file + autoload tools (issue #34).

Read/create/edit Godot resource (`.tres`/`.res`) files and register autoloads, in
the gated `resources_edit` toolset. Distinct from the read-only `godot://` resources
(#11): this is the tool surface for *authoring* resource files. Property values are
coerced by the addon's `type_coerce`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import RESOURCES_EDIT_TAG
from mcp_server.models.resource_files import (
    CreateResourceResult,
    RegisterAutoloadResult,
    ResourceContent,
    SetResourcePropertyResult,
    UnregisterAutoloadResult,
)
from mcp_server.paths import ResPath
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    enforce_preconditions,
    require_confirmation,
)
from mcp_server.tools._route import route, run_or_preview

RESOURCES_EDIT = {RESOURCES_EDIT_TAG}


def register_resource_files(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the resource-file + autoload tools."""

    @mcp.tool(meta=READ_ONLY, tags=RESOURCES_EDIT)
    async def read_resource_file(resource_path: ResPath) -> ResourceContent:
        """Read a resource file (`.tres`/`.res`): its type, attached script, and
        editable properties. (Distinct from the read-only ``godot://`` resources.)
        """
        params = {"resource_path": resource_path}
        return ResourceContent(**await route(bridge, "cmd_read_resource", params))

    @mcp.tool(meta=DESTRUCTIVE, tags=RESOURCES_EDIT)
    @enforce_preconditions
    async def create_resource(
        type: str,
        resource_path: ResPath,
        properties: dict[str, Any] | None = None,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> CreateResourceResult:
        """Create a resource of ``type`` at ``resource_path`` (``.tres``/``.res``), setting
        ``properties`` (coerced to each property's Godot type), and save it.

        Destructive: writes/overwrites the file on disk and is not UndoRedo-tracked
        (``ResourceSaver.save``), so it requires ``confirm=True`` (``dry_run`` previews).
        """
        if not dry_run:
            require_confirmation(confirm, "create_resource")
        params = {"type": type, "resource_path": resource_path, "properties": properties or {}}
        preview = {"resource_path": resource_path, "type": type, "created": False}
        return await run_or_preview(
            dry_run, CreateResourceResult, preview, bridge, "cmd_create_resource", params
        )

    @mcp.tool(meta=MUTATING, tags=RESOURCES_EDIT)
    async def set_resource_property(
        resource_path: ResPath, property: str, value: Any, dry_run: bool = False
    ) -> SetResourcePropertyResult:
        """Set a property on the resource file at ``resource_path`` and re-save it.
        Reversible via the editor's undo.
        ``value`` accepts JSON for the target Godot type — Vector2/3 as
        ``{"x":1,"y":2}``/``[1,2]``, Color as ``{"r":1,"g":0,"b":0,"a":1}`` or
        ``"#ff0000"``, Rect2 as ``{"position":{...},"size":{...}}``, NodePath/StringName
        as a string, primitives as-is. See docs/tool-contracts.md#value-shapes.
        """
        params = {"resource_path": resource_path, "property": property, "value": value}
        preview = {"resource_path": resource_path, "property": property, "value": value}
        return await run_or_preview(
            dry_run, SetResourcePropertyResult, preview, bridge, "cmd_set_resource_property", params
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=RESOURCES_EDIT)
    @enforce_preconditions
    async def register_autoload(
        name: str, path: ResPath, confirm: bool = False, dry_run: bool = False
    ) -> RegisterAutoloadResult:
        """Register an autoload singleton ``name`` pointing at the script/scene ``path``
        (persisted to project settings).

        Destructive: writes project settings to disk (``ProjectSettings.save``) with no
        UndoRedo, so it requires ``confirm=True`` (``dry_run`` previews).
        """
        if not dry_run:
            require_confirmation(confirm, "register_autoload")
        params = {"name": name, "path": path}
        preview = {"name": name, "path": path, "registered": False}
        return await run_or_preview(
            dry_run, RegisterAutoloadResult, preview, bridge, "cmd_register_autoload", params
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=RESOURCES_EDIT)
    @enforce_preconditions
    async def unregister_autoload(
        name: str, confirm: bool = False, dry_run: bool = False
    ) -> UnregisterAutoloadResult:
        """Remove the autoload singleton ``name`` from project settings.

        Destructive: writes project settings to disk with no UndoRedo, so it requires
        ``confirm=True`` (``dry_run`` previews).
        """
        if not dry_run:
            require_confirmation(confirm, "unregister_autoload")
        params = {"name": name}
        preview = {"name": name, "unregistered": False}
        return await run_or_preview(
            dry_run, UnregisterAutoloadResult, preview, bridge, "cmd_unregister_autoload", params
        )
