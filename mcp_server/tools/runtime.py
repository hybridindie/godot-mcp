"""Runtime loop tool (issue #13).

``run_and_capture`` is the agent's build/verify/fix primitive: run the project
headless, capture output, and get back a structured error/warning/output summary.
Tagged ``runtime`` safety class and gated in the ``runtime`` toolset.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import RUNTIME_TAG
from mcp_server.config import ServerConfig
from mcp_server.constraints import TimeoutSeconds
from mcp_server.defaults import (
    DEFAULT_RUN_TIMEOUT_SECONDS,
)
from mcp_server.models.runtime import RunCaptureResult
from mcp_server.runtime import Runner, resolve_project_dir, summarize_run
from mcp_server.safety import RUNTIME, PreconditionError, enforce_preconditions
from mcp_server.tools._progress import safe_info, safe_progress


def register_runtime(mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner) -> None:
    """Register the runtime-loop tool."""

    @mcp.tool(meta=RUNTIME, tags={RUNTIME_TAG}, task=True)
    @enforce_preconditions
    async def run_and_capture(
        scene: str | None = None,
        timeout_seconds: TimeoutSeconds = DEFAULT_RUN_TIMEOUT_SECONDS,
        *,
        ctx: Context,
    ) -> RunCaptureResult:
        """Run the project headless (optionally a specific ``scene`` like
        "res://main.tscn"), wait up to ``timeout_seconds``, then return a summary of
        ``errors`` / ``warnings`` / ``output`` and the exit code. Use this to verify
        a change actually runs and to read back failures.

        WHEN TO USE: You need to verify a scene runs without an editor open
        (CI, automation, smoke test) or you want the full stdout/stderr log.
        WHEN NOT TO USE: You need to simulate input or inspect live state —
        use play_scene() + get_game_scene_tree() / simulate_key() instead.
        """
        if runner.binary is None:
            raise PreconditionError(
                "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
                required="godot_bin",
            )
        project_dir = await resolve_project_dir(bridge, config)
        await safe_info(
            ctx, f"Running {scene or 'main scene'} headless (timeout {timeout_seconds:g}s)…"
        )
        await safe_progress(ctx, 0, 1)
        output = await runner.run(project_dir, scene, float(timeout_seconds))
        await safe_progress(ctx, 1, 1)
        result = summarize_run(output)
        await safe_info(
            ctx,
            f"Run finished: exit={result.exit_code}, "
            f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)",
        )
        return result
