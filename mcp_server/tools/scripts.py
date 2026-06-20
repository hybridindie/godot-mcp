"""Script read/patch tools (issue #10).

Lets an agent read, list, write, and patch GDScript, and check a script for parse
errors — the authoring half of the build/verify/fix loop. Read/write/patch route
through the addon (single path; the editor re-scans after writes, and writes are
UndoRedo-reversible). ``get_parse_errors`` shells out to ``godot --check-only``
(via the runner) because Godot exposes no in-editor API for structured parse
errors. All in the gated ``scripts`` toolset.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import SCRIPTS_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.scripts import (
    NodeScript,
    ParseCheckResult,
    PatchScriptResult,
    ScriptContent,
    ScriptList,
    WriteScriptResult,
)
from mcp_server.runtime import Runner, resolve_project_dir
from mcp_server.safety import MUTATING, READ_ONLY, PreconditionError, enforce_preconditions
from mcp_server.scripts_parse import parse_check_errors
from mcp_server.tools._route import route, run_or_preview

SCRIPTS = {SCRIPTS_TAG}


async def _script_exists(bridge: Bridge, script_path: str) -> bool:
    """Read-only existence probe for a script (for write_script's dry_run overwrite
    signal). Reads the file; a successful read means it exists (#205)."""
    response = await bridge.send("cmd_read_script", {"script_path": script_path})
    return bool(response.ok)


def register_scripts(mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner) -> None:
    """Register the script read/patch tools."""

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def read_script(script_path: str) -> ScriptContent:
        """Read the full text of the GDScript at ``script_path`` (a ``res://`` path)."""
        return ScriptContent(**await route(bridge, "cmd_read_script", {"script_path": script_path}))

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def list_scripts(directory: str = "res://") -> ScriptList:
        """List all ``.gd`` files under ``directory`` (recursive, ``res://`` path)."""
        return ScriptList(**await route(bridge, "cmd_list_scripts", {"directory": directory}))

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def get_script_for_node(node_path: str = "") -> NodeScript:
        """Get the script attached to a node (by scene-relative ``node_path``, or the
        selected node when omitted). ``script_path``/``content`` are null if none.
        """
        result = await route(bridge, "cmd_get_script_for_node", {"node_path": node_path})
        return NodeScript(**result)

    @mcp.tool(meta=MUTATING, tags=SCRIPTS)
    async def write_script(
        script_path: str, content: str, dry_run: bool = False
    ) -> WriteScriptResult:
        """Create or overwrite the GDScript at ``script_path`` with ``content``.
        Reversible via the editor's undo. ``dry_run=True`` writes nothing and reports
        ``would_overwrite`` so the agent knows whether it is about to replace an
        existing script.
        """
        params = {"script_path": script_path, "content": content}
        if dry_run:
            exists = await _script_exists(bridge, script_path)
            return WriteScriptResult(
                script_path=script_path, created=not exists, would_overwrite=exists, dry_run=True
            )
        return WriteScriptResult(**await route(bridge, "cmd_write_script", params))

    @mcp.tool(meta=MUTATING, tags=SCRIPTS)
    async def patch_script(
        script_path: str, find: str, replace: str, dry_run: bool = False
    ) -> PatchScriptResult:
        """Replace every occurrence of ``find`` with ``replace`` in the script.
        Errors if ``find`` isn't present. Reversible via undo; ``dry_run`` previews.
        """
        params = {"script_path": script_path, "find": find, "replace": replace}
        preview = {"script_path": script_path, "replacements": 0}
        return await run_or_preview(
            dry_run, PatchScriptResult, preview, bridge, "cmd_patch_script", params
        )

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    @enforce_preconditions
    async def get_parse_errors(script_path: str) -> ParseCheckResult:
        """Parse-check ``script_path`` and return structured errors (message + line),
        or an empty list when it parses cleanly. Use after writing/patching a script.
        """
        if runner.binary is None:
            raise PreconditionError(
                "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
                required="godot_bin",
            )
        project_dir = await resolve_project_dir(bridge, config)
        output = await runner.check_script(project_dir, script_path, timeout=30.0)
        errors = parse_check_errors(output.stdout + "\n" + output.stderr)
        return ParseCheckResult(script_path=script_path, ok=not errors, errors=errors)
