"""Project & filesystem tools (issue #32).

Explore the project on disk, search files, read/write project settings, and resolve
resource UIDs. Gated `project` toolset. Reads are `read_only`; `set_setting` is
`mutating` (persists to project settings); `delete_resource_file` is `destructive`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PROJECT_TAG
from mcp_server.constraints import MaxDepth, MaxResults
from mcp_server.defaults import (
    DEFAULT_SEARCH_MAX_RESULTS,
)
from mcp_server.models.project_fs import (
    DeleteResourceFileResult,
    FilesystemTree,
    SearchResult,
    SetSettingResult,
    SettingValue,
    UidResolution,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    enforce_preconditions,
    require_bridge_connected,
    require_confirmation,
)
from mcp_server.tools._route import route, run_or_preview, validate_or_raise

PROJECT = {PROJECT_TAG}


def register_project_fs(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the project & filesystem tools."""

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    async def get_filesystem_tree(
        directory: str = "res://", max_depth: MaxDepth = -1
    ) -> FilesystemTree:
        """Get the project's file tree under ``directory`` ({name, path, type, children}).
        ``max_depth`` limits levels (-1 = unlimited, 0 = the directory only). Hidden
        entries (``.godot``, ``.git``, …) are skipped.
        """
        params = {"directory": directory, "max_depth": max_depth}
        return FilesystemTree(**await route(bridge, "cmd_get_filesystem_tree", params))

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    async def search_files(
        directory: str = "res://",
        name_glob: str = "",
        content: str = "",
        max_results: MaxResults = DEFAULT_SEARCH_MAX_RESULTS,
    ) -> SearchResult:
        """Search ``directory`` recursively for files matching ``name_glob`` (e.g.
        "*.gd") and/or containing ``content``. ``truncated`` is true if capped at
        ``max_results``.
        """
        params = {
            "directory": directory,
            "name_glob": name_glob,
            "content": content,
            "max_results": max_results,
        }
        return SearchResult(**await route(bridge, "cmd_search_files", params))

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    async def get_setting(name: str) -> SettingValue:
        """Read a project setting by name (e.g. "application/config/name").
        ``exists=false`` (value null) when the setting is not set.
        """
        return SettingValue(**await route(bridge, "cmd_get_setting", {"name": name}))

    @mcp.tool(meta=MUTATING, tags=PROJECT)
    async def set_setting(name: str, value: Any, dry_run: bool = False) -> SetSettingResult:
        """Set a project setting and persist it. Coerced to the setting's existing type
        when it already exists. Not undo-tracked (it writes project settings).
        ``value`` accepts JSON for the target Godot type — Vector2/3 as
        ``{"x":1,"y":2}``/``[1,2]``, Color as ``{"r":1,"g":0,"b":0,"a":1}`` or
        ``"#ff0000"``, Rect2 as ``{"position":{...},"size":{...}}``, NodePath/StringName
        as a string, primitives as-is. See docs/tool-contracts.md#value-shapes.
        """
        params = {"name": name, "value": value}
        preview = {"name": name, "value": value, "set": False}
        return await run_or_preview(
            dry_run, SetSettingResult, preview, bridge, "cmd_set_setting", params
        )

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    async def resolve_uid(value: str) -> UidResolution:
        """Resolve between a resource path and its UID. Pass a ``uid://…`` string to get
        the path, or a ``res://…`` path to get its UID.
        """
        if value.startswith("uid://"):
            result = await route(bridge, "cmd_uid_to_path", {"uid": value})
        else:
            result = await route(bridge, "cmd_path_to_uid", {"path": value})
        return UidResolution(uid=result.get("uid"), path=result.get("path"))

    @mcp.tool(meta=DESTRUCTIVE, tags=PROJECT)
    @enforce_preconditions
    async def delete_resource_file(
        path: str, confirm: bool = False, dry_run: bool = False
    ) -> DeleteResourceFileResult:
        """Delete the ``res://`` file at ``path`` (and its ``.uid`` sidecar). The inverse
        of the file-creating tools (create_scene, create_resource, create_tileset,
        import_asset, …) — use it to roll back a file you just generated.

        DESTRUCTIVE: requires ``confirm=True`` to actually delete; ``dry_run=True``
        previews without confirming or deleting. ``res://`` containment is enforced (a
        traversal or non-``res://`` path is rejected). Undoable in the editor (the file
        bytes are restored on undo). Errors RESOURCE_NOT_FOUND if no file is at ``path``.
        """
        require_bridge_connected(bridge)
        params = {"path": path}
        if dry_run:
            # Validate containment even on a dry_run so it can't preview an escaping
            # path (parity with the script-write hardening, #205).
            await validate_or_raise(bridge, "cmd_delete_resource_file", params)
            return DeleteResourceFileResult(path=path, deleted=False, dry_run=True)
        require_confirmation(confirm, "delete_resource_file")
        return DeleteResourceFileResult(
            **await route(bridge, "cmd_delete_resource_file", params)
        )
