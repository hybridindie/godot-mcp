"""Project & filesystem tools (issue #32).

Explore the project on disk, search files, read/write project settings, and resolve
resource UIDs. Gated `project` toolset. Reads are `read_only`; `set_setting` is
`mutating` (persists to project settings).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PROJECT_TAG
from mcp_server.models.project_fs import (
    FilesystemTree,
    SearchResult,
    SetSettingResult,
    SettingValue,
    UidResolution,
)
from mcp_server.safety import MUTATING, READ_ONLY
from mcp_server.tools._route import route

PROJECT = {PROJECT_TAG}


def register_project_fs(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the project & filesystem tools."""

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    async def get_filesystem_tree(directory: str = "res://", max_depth: int = -1) -> FilesystemTree:
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
        max_results: int = 200,
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
        """
        if dry_run:
            return SetSettingResult(name=name, value=value, set=False, dry_run=True)
        result = await route(bridge, "cmd_set_setting", {"name": name, "value": value})
        return SetSettingResult(**result)

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
