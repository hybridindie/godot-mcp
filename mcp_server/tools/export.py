"""Export tools (issue #50).

Drive Godot's export pipeline: list export presets and report export info (read from the
project's ``export_presets.cfg`` via the addon), and run an export. ``export_project``
launches a Godot process via the runner (process execution, like the runtime loop #13 —
see the architecture note there), so it's `runtime` and uses a generous timeout. Gated
`export` toolset. Requires export templates installed for the target platform.
"""

from __future__ import annotations

import os

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
from mcp_server.paths import ExportPath
from mcp_server.runtime import Runner, resolve_project_dir, summarize_run
from mcp_server.safety import (
    READ_ONLY,
    RUNTIME,
    enforce_preconditions,
    require_godot_binary,
)
from mcp_server.tools._progress import safe_info, safe_progress
from mcp_server.tools._route import route

EXPORT = {EXPORT_TAG}


def _guard_export_output(project_dir: str, output_path: str, confirm: bool) -> None:
    """Refuse an export target outside the project dir unless ``confirm=True`` (#637).

    Export output legitimately can be a filesystem path (often outside the
    project), so it is not a ``res://`` path — but an un-gated arbitrary write
    target is a real risk. A relative path resolves against ``project_dir``;
    anything that lands outside it needs an explicit ``confirm``.
    """
    candidate = (
        output_path if os.path.isabs(output_path) else os.path.join(project_dir, output_path)
    )
    resolved = os.path.normpath(candidate)
    root = os.path.normpath(project_dir)
    contained = resolved == root or resolved.startswith(root + os.sep)
    if not contained and not confirm:
        raise ToolError(
            f"VALIDATION_ERROR: output_path '{output_path}' is outside the project dir "
            f"('{project_dir}'). Pass confirm=True to export outside the project. "
            "[required=confirm]"
        )


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

    @mcp.tool(meta=RUNTIME, tags=EXPORT, task=True)
    @enforce_preconditions
    async def export_project(
        preset: str,
        output_path: ExportPath,
        debug: bool = False,
        confirm: bool = False,
        timeout_seconds: TimeoutSeconds = DEFAULT_EXPORT_TIMEOUT_SECONDS,
        *,
        ctx: Context,
    ) -> ExportResult:
        """Export the project with the named ``preset`` to ``output_path`` (relative paths
        resolve against the project dir). ``debug`` does a debug export. Runs Godot headless
        — requires export templates installed; returns the exit code and parsed
        errors/warnings. Use a generous ``timeout_seconds`` (exports can be slow).

        ``output_path`` is confined to the project dir: a target outside it (an absolute
        path, or a relative path that climbs out) is refused unless ``confirm=True``.
        """
        require_godot_binary(runner.binary)
        presets = ExportPresetsResult(**await route(bridge, "cmd_list_export_presets", {}))
        names = [p.name for p in presets.presets]
        if preset not in names:
            raise ToolError(f"No export preset named '{preset}'. Available: {names}.")
        project_dir = await resolve_project_dir(bridge, config)
        _guard_export_output(project_dir, output_path, confirm)
        await safe_info(
            ctx,
            f"Exporting preset '{preset}' → {output_path} (timeout {timeout_seconds:g}s)…",
        )
        await safe_progress(ctx, 0, 1)
        run = await runner.export(project_dir, preset, output_path, debug, float(timeout_seconds))
        await safe_progress(ctx, 1, 1)
        summary = summarize_run(run)
        await safe_info(
            ctx,
            f"Export finished: exit={summary.exit_code}, "
            f"{len(summary.errors)} error(s), {len(summary.warnings)} warning(s)",
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
