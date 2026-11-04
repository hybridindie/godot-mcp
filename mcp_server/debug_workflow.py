"""Debug-workflow service: aggregate read-only diagnostics into one report.

The ``debug_workflow`` tool is a thin delegator (per
.claude/rules/architecture.md — tool bodies hold no domain logic); all the work
lives here as small, independently testable pieces:

- ``collect_parse_errors`` / ``collect_scene_tree`` / ``collect_run`` /
  ``collect_bridge_info`` gather one diagnostic each,
- ``build_report`` is a pure function turning those into findings/suggestions,
- ``run_debug_workflow`` orchestrates them and assembles the result model.
"""

from __future__ import annotations

from typing import Any

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.debug_workflow import DebugWorkflowResult
from mcp_server.models.runtime import RunCaptureResult
from mcp_server.models.scripts import ParseError
from mcp_server.runtime import Runner, resolve_project_dir, summarize_run
from mcp_server.scripts_parse import parse_check_errors
from mcp_server.tools._route import route


async def collect_parse_errors(
    bridge: Bridge, config: ServerConfig, runner: Runner
) -> tuple[list[ParseError], str | None]:
    """Parse-check every GDScript file. Returns (errors, skipped_reason)."""
    if runner.binary is None:
        return [], "Godot binary not found — cannot parse-check scripts."
    parse_errors: list[ParseError] = []
    try:
        project_dir = await resolve_project_dir(bridge, config)
        scripts_response = await bridge.send("cmd_list_scripts", {"directory": "res://"})
        if scripts_response.ok and scripts_response.result:
            for script_path in scripts_response.result.get("scripts", []):
                try:
                    output = await runner.check_script(project_dir, script_path, timeout=15.0)
                    parse_errors.extend(parse_check_errors(output.stdout + "\n" + output.stderr))
                except Exception:
                    pass  # Skip individual scripts that fail to check
    except Exception as exc:
        return parse_errors, str(exc)
    return parse_errors, None


async def collect_scene_tree(bridge: Bridge) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch the active scene tree. Returns ``(tree, error)``.

    A failed command must not be reported as "no scene is open" — the caller
    gets the cause and surfaces it (#796).
    """
    try:
        tree_response = await route(bridge, "cmd_get_scene_tree", {"max_depth": -1})
        if tree_response:
            return tree_response, None
        return None, None
    except Exception as exc:
        return None, str(exc)


async def collect_run(
    bridge: Bridge, config: ServerConfig, runner: Runner, scene: str, timeout_seconds: float
) -> tuple[RunCaptureResult | None, str | None]:
    """Headless-run the project/scene. Returns (summary, skipped_reason)."""
    if runner.binary is None:
        return None, None
    try:
        project_dir = await resolve_project_dir(bridge, config)
        output = await runner.run(project_dir, scene or None, float(timeout_seconds))
        return summarize_run(output), None
    except Exception as exc:
        # Can't resolve project dir (no editor, no env var) — report it as a finding.
        return None, str(exc)


async def collect_bridge_info(bridge: Bridge) -> tuple[dict[str, Any], str | None]:
    """Bridge connectivity plus project/version info. Returns ``(info, error)``.

    ``connected`` is the transport's view; ``error`` names why the project-info
    probe failed, so the report doesn't silently look healthy (#796).
    """
    bridge_info: dict[str, Any] = {"connected": bridge.connected}
    try:
        info_response = await route(bridge, "cmd_get_project_info")
        if info_response:
            bridge_info = {
                "connected": True,
                "godot_version": info_response.get("godot_version"),
                "project_name": info_response.get("name"),
                "main_scene": info_response.get("main_scene"),
                "autoloads": info_response.get("autoloads"),
            }
    except Exception as exc:
        return bridge_info, str(exc)
    return bridge_info, None


def build_report(
    *,
    bridge_connected: bool,
    tree_result: dict[str, Any] | None,
    run_result: RunCaptureResult | None,
    run_skipped: str | None,
    parse_errors: list[ParseError],
    parse_skipped: str | None,
    expected_timeout: bool = False,
    tree_error: str | None = None,
    bridge_error: str | None = None,
) -> tuple[list[str], list[str]]:
    """Turn the collected diagnostics into (findings, suggestions). Pure.

    ``expected_timeout`` marks runs of games that legitimately never quit on
    their own (sandbox/live-service games): a timeout then means the game ran
    as designed, so no timeout finding is emitted (issue #490).

    ``tree_error``/``bridge_error`` carry why a probe failed (#796). A failed
    probe is never reported as the *symptom* ("no scene open", "disconnected"),
    because that sends the agent to the wrong fix.
    """
    findings: list[str] = []
    suggestions: list[str] = []

    if run_skipped:
        findings.append(f"HEADLESS RUN SKIPPED: {run_skipped}")

    if not bridge_connected:
        findings.append("BRIDGE DISCONNECTED: Godot editor is not reachable.")
        suggestions.append(
            "Open Godot with the addon enabled\n"
            "(Project Settings → Plugins → godot_mcp → Enable)."
        )
    elif bridge_error:
        findings.append(f"BRIDGE INFO UNAVAILABLE: {bridge_error}")
        suggestions.append(
            "The bridge is connected but the project-info probe failed — call "
            "godot_health_check() to inspect the bridge/editor state, then retry."
        )

    if tree_result is None or not tree_result.get("tree"):
        if tree_error:
            findings.append(f"SCENE TREE UNAVAILABLE: {tree_error}")
            suggestions.append(
                "The scene-tree request failed — call godot_health_check() to check "
                "the bridge/editor state, then retry."
            )
        else:
            findings.append("NO ACTIVE SCENE: No .tscn scene is currently open in the editor.")
            suggestions.append(
                "Open a scene in Godot or call godot_scene_edit_create_scene("
                "root_type=…, scene_path=…) to make one (enable the scene_edit toolset first)."
            )

    if run_result:
        if run_result.errors:
            findings.append(
                f"RUNTIME ERRORS: {len(run_result.errors)} error(s) captured "
                "during headless run."
            )
            for err in run_result.errors[:3]:
                suggestions.append(
                    f"  [{err.type.upper()}] {err.message}"
                    + (f" at {err.source}:{err.line}" if err.source else "")
                )
        if run_result.warnings:
            findings.append(
                f"RUNTIME WARNINGS: {len(run_result.warnings)} warning(s) captured."
            )
        if run_result.timed_out and not expected_timeout:
            findings.append("RUN TIMED OUT: The game did not exit within the timeout.")
            suggestions.append(
                "If the game should quit on its own, check for missing quit() calls "
                "or stuck loops in _process/_physics_process. If it is meant to run "
                "indefinitely (sandbox/live-service), pass expected_timeout=true so "
                "the timeout is not reported as an issue."
            )
        # exit_code is None when the run was killed by the timeout — that is not a
        # crash, so only a real non-zero exit is a finding (issue #490).
        if not run_result.timed_out and run_result.exit_code not in (None, 0):
            findings.append(
                f"NON-ZERO EXIT: headless run exited with code {run_result.exit_code}."
            )

    if parse_errors:
        findings.append(f"PARSE ERRORS: {len(parse_errors)} script(s) failed parse check.")
        for pe in parse_errors[:3]:
            suggestions.append(
                f"  [PARSE] {pe.message}"
                + (f" at {pe.source}:{pe.line}" if pe.source else "")
            )
    elif parse_skipped:
        findings.append(f"PARSE CHECK SKIPPED: {parse_skipped}")

    if not findings:
        findings.append("No obvious issues detected. The project appears healthy.")
    if not suggestions:
        suggestions.append("Consider running run_test_scenario() for deeper play-testing.")

    return findings, suggestions


async def run_debug_workflow(
    bridge: Bridge,
    config: ServerConfig,
    runner: Runner,
    scene: str,
    timeout_seconds: float,
    expected_timeout: bool = False,
) -> DebugWorkflowResult:
    """Run all diagnostics and assemble the unified report model."""
    parse_errors, parse_skipped = await collect_parse_errors(bridge, config, runner)
    tree_result, tree_error = await collect_scene_tree(bridge)
    run_result, run_skipped = await collect_run(bridge, config, runner, scene, timeout_seconds)
    bridge_info, bridge_error = await collect_bridge_info(bridge)

    findings, suggestions = build_report(
        bridge_connected=bridge.connected,
        tree_result=tree_result,
        run_result=run_result,
        run_skipped=run_skipped,
        parse_errors=parse_errors,
        parse_skipped=parse_skipped,
        expected_timeout=expected_timeout,
        tree_error=tree_error,
        bridge_error=bridge_error,
    )

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
