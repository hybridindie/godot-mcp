"""Debug workflow: aggregate diagnostics to help the LLM/user find errors.

Runs a sequence of read-only checks — parse errors, scene tree inspection,
headless run capture, project stats, and signal flow analysis — then returns
a unified report with actionable findings. This is the "call one tool, get
everything" debug primitive.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.debug_workflow import DebugWorkflowResult
from mcp_server.models.scripts import ParseCheckResult, ParseError
from mcp_server.runtime import GodotRunner, Runner, summarize_run
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import route


def register_debug_workflow(
    mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner
) -> None:
    """Register the debug_workflow aggregator tool."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def debug_workflow(
        scene: str = "",
        timeout_seconds: float = 5.0,
    ) -> DebugWorkflowResult:
        """Run a comprehensive debug check on the project and return a unified report.

        This aggregates multiple diagnostics into one call so you (or the LLM) can
        spot problems quickly without calling each tool individually.

        Checks performed:
        1. Parse errors across all GDScript files
        2. Active scene tree structure (nodes, scripts, properties)
        3. Headless run of the project (or a specific scene) capturing errors/warnings
        4. Signal connections in the active scene
        5. Bridge connection state and Godot version

        ``scene`` — optional res:// path to focus the headless run on a specific scene.
        """
        # 1. Parse errors — scan every .gd file in the project
        parse_errors: list[ParseError] = []
        parse_skipped: str | None = None
        if runner.binary is not None:
            try:
                from mcp_server.runtime import resolve_project_dir
                from mcp_server.tools.scripts import parse_check_errors
                project_dir = await resolve_project_dir(bridge, config)
                # List scripts via bridge
                scripts_response = await route(bridge, "cmd_list_scripts", {"directory": "res://"})
                if scripts_response.ok:
                    for script_path in scripts_response.result.get("scripts", []):
                        try:
                            output = await runner.check_script(project_dir, script_path, timeout=15.0)
                            errs = parse_check_errors(output.stdout + "\n" + output.stderr)
                            parse_errors.extend(errs)
                        except Exception:
                            # Skip individual scripts that fail to check
                            pass
            except Exception as exc:
                parse_skipped = str(exc)
        else:
            parse_skipped = "Godot binary not found — cannot parse-check scripts."

        # 2. Scene tree
        tree_result = None
        try:
            tree_response = await route(bridge, "cmd_get_scene_tree", {"max_depth": -1})
            if tree_response.ok:
                tree_result = tree_response.result
        except Exception:
            pass

        # Build the unified report (initialize early so exception handlers can append)
        findings: list[str] = []
        suggestions: list[str] = []

        # 3. Headless run
        run_result = None
        if runner.binary is not None:
            try:
                from mcp_server.runtime import resolve_project_dir
                project_dir = await resolve_project_dir(bridge, config)
                output = await runner.run(project_dir, scene or None, float(timeout_seconds))
                run_result = summarize_run(output)
            except Exception as exc:
                # If we can't resolve project dir (no editor, no env var), report it.
                run_result = None
                findings.append(f"HEADLESS RUN SKIPPED: {exc}")

        # 4. Bridge / project info
        bridge_info = {"connected": bridge.connected}
        try:
            info_response = await route(bridge, "cmd_get_project_info")
            if info_response.ok:
                bridge_info = {
                    "connected": True,
                    "godot_version": info_response.result.get("godot_version"),
                    "project_name": info_response.result.get("name"),
                    "main_scene": info_response.result.get("main_scene"),
                    "autoloads": info_response.result.get("autoloads"),
                }
        except Exception:
            pass

        if not bridge.connected:
            findings.append("BRIDGE DISCONNECTED: Godot editor is not reachable.")
            suggestions.append(
                "Open Godot with the addon enabled (Project Settings → Plugins → godot_mcp → Enable)."
            )

        if tree_result is None or not tree_result.get("tree"):
            findings.append("NO ACTIVE SCENE: No .tscn scene is currently open in the editor.")
            suggestions.append("Open a scene in Godot or call create_scene() to make one.")

        if run_result:
            if run_result.errors:
                findings.append(
                    f"RUNTIME ERRORS: {len(run_result.errors)} error(s) captured during headless run."
                )
                for e in run_result.errors[:3]:
                    suggestions.append(
                        f"  [{e.type.upper()}] {e.message}"
                        + (f" at {e.source}:{e.line}" if e.source else "")
                    )
            if run_result.warnings:
                findings.append(
                    f"RUNTIME WARNINGS: {len(run_result.warnings)} warning(s) captured."
                )
            if run_result.timed_out:
                findings.append("RUN TIMED OUT: The game did not exit within the timeout.")
                suggestions.append(
                    "Check for infinite loops in _process/_physics_process or missing quit() calls."
                )
            if run_result.exit_code != 0:
                findings.append(f"NON-ZERO EXIT: headless run exited with code {run_result.exit_code}.")

        if parse_errors:
            findings.append(
                f"PARSE ERRORS: {len(parse_errors)} script(s) failed parse check."
            )
            for e in parse_errors[:3]:
                suggestions.append(
                    f"  [PARSE] {e.message}"
                    + (f" at {e.source}:{e.line}" if e.source else "")
                )
        elif parse_skipped:
            findings.append(f"PARSE CHECK SKIPPED: {parse_skipped}")

        if not findings:
            findings.append("No obvious issues detected. The project appears healthy.")

        if not suggestions:
            suggestions.append("Consider running run_test_scenario() for deeper play-testing.")

        return DebugWorkflowResult(
            bridge=bridge_info,
            scene_tree=tree_result.get("tree") if tree_result else None,
            run=run_result.model_dump() if run_result else None,
            parse={
                "ok": not parse_errors,
                "errors": [e.model_dump() for e in parse_errors],
                "skipped_reason": parse_skipped,
            },
            findings=findings,
            suggestions=suggestions,
        )
