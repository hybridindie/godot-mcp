"""Project scaffold tool (issue #112).

Generates a project skeleton (directories, settings, autoloads, root scene)
for common game types so agents start from a known structure instead of a
blank project.  This is not a template system — it creates empty nodes,
generic scripts, and configuration values that the agent can build on with
existing tools.

Gated ``project_scaffold`` toolset.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import PROJECT_SCAFFOLD_TAG
from mcp_server.models.project_scaffold import ScaffoldProjectResult
from mcp_server.safety import DESTRUCTIVE, enforce_preconditions, require_confirmation
from mcp_server.tools._route import run_or_preview

PROJECT_SCAFFOLD = {PROJECT_SCAFFOLD_TAG}

# Supported scaffold types.
_SCAFFOLD_TYPES: set[str] = {
    "2d_platformer",
    "3d_fps",
    "top_down_rpg",
    "visual_novel",
}


# ---------------------------------------------------------------------------
# Public tool registration
# ---------------------------------------------------------------------------


def register_project_scaffold(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the project scaffold tool."""

    @mcp.tool(meta=DESTRUCTIVE, tags=PROJECT_SCAFFOLD)
    @enforce_preconditions
    async def scaffold_project(
        type: str,
        project_name: str = "",
        main_scene: str = "",
        confirm: bool = False,
        dry_run: bool = False,
    ) -> ScaffoldProjectResult:
        """Scaffold a project skeleton for ``type``.

        Supported types: ``"2d_platformer"`` | ``"3d_fps"`` | ``"top_down_rpg"`` |
        ``"visual_novel"``.  Creates directories, sets rendering/window defaults,
        registers autoloads, and creates a root scene.  Requires ``confirm=True``
        because it mutates the project filesystem broadly.
        """
        if type not in _SCAFFOLD_TYPES:
            raise ValueError(
                f"Unknown scaffold type '{type}'. Supported: {_SCAFFOLD_TYPES}."
            )
        if not dry_run:
            require_confirmation(confirm, "scaffold_project")
        params: dict[str, str] = {
            "type": type,
            "project_name": project_name or type,
            "main_scene": main_scene or "main",
        }
        preview = {
            "created": False,
            "paths_created": [],
            "autoloads_registered": [],
        }
        return await run_or_preview(
            dry_run,
            ScaffoldProjectResult,
            preview,
            bridge,
            "cmd_scaffold_project",
            params,
        )
