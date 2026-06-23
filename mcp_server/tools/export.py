"""Export tools (issue #50).

Drive Godot's export pipeline: list export presets and report export info (read from the
project's ``export_presets.cfg`` via the addon), and run an export. ``export_project``
launches a Godot process via the runner (process execution, like the runtime loop #13 —
see the architecture note there), so it's `runtime` and uses a generous timeout. Gated
`export` toolset. Requires export templates installed for the target platform.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import EXPORT_TAG
from mcp_server.config import ServerConfig
from mcp_server.constraints import TimeoutSeconds
from mcp_server.defaults import (
    DEFAULT_EXPORT_TIMEOUT_SECONDS,
)
from mcp_server.models.export import ExportInfoResult, ExportPresetsResult, ExportResult
from mcp_server.runtime import Runner, resolve_project_dir, summarize_run
from mcp_server.safety import READ_ONLY, RUNTIME, PreconditionError, enforce_preconditions
from mcp_server.tools._route import route

EXPORT = {EXPORT_TAG}


def register_export(mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner) -> None:
    """Register the export tools."""

    @mcp.tool(meta=READ_ONLY, tags=EXPORT)
    async def list_export_presets() -> ExportPresetsResult:
        """List the project's export presets (from ``export_presets.cfg``): each preset's
        index, name, platform, runnable flag, and configured export_path.
        """
        return ExportPresetsResult(**await route(bridge, "cmd_list_export_presets", {}))

    @mcp.tool(meta=READ_ONLY, tags=EXPORT)
    async def get_export_info() -> ExportInfoResult:
        """Summarize export configuration: whether ``export_presets.cfg`` exists, the
        preset count, and preset names. Use it before ``export_project``.
        """
        return ExportInfoResult(**await route(bridge, "cmd_get_export_info", {}))

    @mcp.tool(meta=RUNTIME, tags=EXPORT)
    @enforce_preconditions
    async def export_project(
        preset: str,
        output_path: str,
        debug: bool = False,
        timeout_seconds: TimeoutSeconds = DEFAULT_EXPORT_TIMEOUT_SECONDS,
        *,
        ctx: Context,
    ) -> ExportResult:
        """Export the project with the named ``preset`` to ``output_path`` (relative paths
        resolve against the project dir). ``debug`` does a debug export. Runs Godot headless
        — requires export templates installed; returns the exit code and parsed
        errors/warnings. Use a generous ``timeout_seconds`` (exports can be slow).
        """
        if runner.binary is None:
            raise PreconditionError(
                "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
                required="godot_bin",
            )
        presets = ExportPresetsResult(**await route(bridge, "cmd_list_export_presets", {}))
        names = [p.name for p in presets.presets]
        if preset not in names:
            raise ToolError(f"No export preset named '{preset}'. Available: {names}.")
        project_dir = await resolve_project_dir(bridge, config)
        await ctx.info(
            f"Exporting preset '{preset}' → {output_path} (timeout {timeout_seconds:g}s)…"
        )
        await ctx.report_progress(0, 1)
        run = await runner.export(project_dir, preset, output_path, debug, float(timeout_seconds))
        await ctx.report_progress(1, 1)
        summary = summarize_run(run)
        await ctx.info(
            f"Export finished: exit={summary.exit_code}, "
            f"{len(summary.errors)} error(s), {len(summary.warnings)} warning(s)"
        )
        return ExportResult(
            exported=summary.exit_code == 0 and not summary.timed_out,
            preset=preset,
            output_path=output_path,
            exit_code=summary.exit_code,
            timed_out=summary.timed_out,
            duration_seconds=summary.duration_seconds,
            errors=summary.errors,
            warnings=summary.warnings,
            output=summary.output,
            command=summary.command,
        )
