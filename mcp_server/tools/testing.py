"""Testing / QA tools (issue #37).

Automated play-testing, built entirely on existing capabilities (no new addon commands):
assert live node state, run an input-scenario with assertions, fuzz with random input,
and diff screenshots. Gated `testing` toolset. Scenario/stress control the run
(`runtime`); assertions and screenshot diff are `read_only`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import TESTING_TAG
from mcp_server.config import ServerConfig
from mcp_server.constraints import DelayMs, StressIterations, TimeoutMs, TimeoutSeconds
from mcp_server.defaults import (
    DEFAULT_ASSERT_NODE_TIMEOUT_MS,
    DEFAULT_PROBE_POLL_INTERVAL_SECONDS,
    DEFAULT_STRESS_BUFFER_SECONDS,
    DEFAULT_STRESS_DELAY_MS,
    DEFAULT_STRESS_ITERATIONS,
    DEFAULT_STRESS_MAX_WAIT_SECONDS,
    DEFAULT_TEST_RUN_TIMEOUT_SECONDS,
    DEFAULT_TEST_SETTLE_MS,
    DEFAULT_TEST_SETUP_MS,
)
from mcp_server.gut_parse import parse_gut_results
from mcp_server.models.testing import (
    AssertionResult,
    RunTestsResult,
    ScenarioResult,
    ScreenshotDiffResult,
    StressTestResult,
)
from mcp_server.qa import ImageCompareError, compare_images, evaluate_assertion, random_input_events
from mcp_server.runtime import Runner, resolve_project_dir
from mcp_server.safety import READ_ONLY, RUNTIME, PreconditionError
from mcp_server.tools._progress import safe_info, safe_progress
from mcp_server.tools._route import poll_ready, route

TESTING = {TESTING_TAG}


async def _read_live_value(
    bridge: Bridge, node_path: str, prop: str, timeout_ms: int
) -> tuple[Any, str]:
    """One-shot read of a live property by reusing monitor_property with a single sample.

    Returns (value, error): error is set when the node/property was invalid or no sample
    arrived in time.
    """
    await route(
        bridge, "cmd_monitor_property", {"node_path": node_path, "property": prop, "samples": 1}
    )
    result = await poll_ready(bridge, "cmd_get_property_samples", {}, timeout_ms)
    if result.get("error"):
        return None, str(result["error"])
    samples = result.get("samples") or []
    if not result.get("ready") or not samples:
        return None, "no sample captured (is the game still running?)"
    return samples[0].get("value"), ""


async def _assert_one(bridge: Bridge, spec: dict[str, Any], timeout_ms: int) -> AssertionResult:
    node_path = str(spec.get("node_path", ""))
    prop = str(spec.get("property", ""))
    op = str(spec.get("op", "=="))
    expected = spec.get("expected")
    value, error = await _read_live_value(bridge, node_path, prop, timeout_ms)
    passed = False if error else evaluate_assertion(value, expected, op)
    return AssertionResult(
        node_path=node_path,
        property=prop,
        op=op,
        expected=expected,
        actual=value,
        passed=passed,
        error=error,
    )


async def _wait_connected(bridge: Bridge, timeout_ms: int) -> bool:
    poll_interval_ms = int(DEFAULT_PROBE_POLL_INTERVAL_SECONDS * 1000)
    deadline_attempts = max(1, timeout_ms // poll_interval_ms)
    for _ in range(deadline_attempts):
        state = await route(bridge, "cmd_get_game_scene_tree", {})
        if state.get("connected"):
            return True
        await asyncio.sleep(DEFAULT_PROBE_POLL_INTERVAL_SECONDS)
    return False


def _gut_present(project_dir: str) -> bool:
    """True when the project has GUT installed (its command-line runner exists)."""
    return (Path(project_dir) / "addons" / "gut" / "gut_cmdln.gd").is_file()


def register_testing(mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner) -> None:
    """Register the testing / QA tools."""

    @mcp.tool(meta=RUNTIME, tags=TESTING)
    async def run_tests(
        test_dir: str = "res://test",
        timeout_seconds: TimeoutSeconds = DEFAULT_TEST_RUN_TIMEOUT_SECONDS,
        *,
        ctx: Context,
    ) -> RunTestsResult:
        """Run the project's GDScript test suite (GUT) headlessly and return a
        structured result: ``passed``/``failed``/``total``, per-failure detail, and
        the raw summary. A neutral capability — it executes tests and reports; it
        does not decide a workflow. ``test_dir`` is the GUT test directory.

        Returns ``framework_absent=true`` (not an error) when GUT is not installed
        (no ``res://addons/gut/``), so the caller can fall back.

        WHEN TO USE: verify behavior against the project's existing tests.
        WHEN NOT TO USE: there is no test suite — write one first, or use
        run_and_capture / get_parse_errors for a smoke/parse check.
        """
        if runner.binary is None:
            raise PreconditionError(
                "Godot binary not found. Set GODOT_MCP_GODOT_BIN to your Godot executable.",
                required="godot_bin",
            )
        project_dir = await resolve_project_dir(bridge, config)
        if not _gut_present(project_dir):
            return RunTestsResult(ran=False, framework="gut", framework_absent=True)
        await safe_info(ctx, f"Running GUT suite in {test_dir} (timeout {timeout_seconds:g}s)…")
        await safe_progress(ctx, 0, 1)
        output = await runner.run_tests(project_dir, test_dir, timeout=float(timeout_seconds))
        await safe_progress(ctx, 1, 1)
        if output.timed_out:
            await safe_info(ctx, "Test run timed out")
            return RunTestsResult(
                ran=True, framework="gut", timed_out=True, raw_summary=output.stdout.strip()[-2000:]
            )
        result = parse_gut_results(output.stdout)
        result.exit_code = output.exit_code
        await safe_info(ctx, f"Tests finished: {result.passed} passed, {result.failed} failed")
        return result

    @mcp.tool(meta=READ_ONLY, tags=TESTING)
    async def assert_node_state(
        node_path: str,
        property: str,
        expected: Any,
        op: str = "==",
        timeout_ms: TimeoutMs = DEFAULT_ASSERT_NODE_TIMEOUT_MS,
    ) -> AssertionResult:
        """Assert that a *running* game node's ``property`` satisfies ``op`` vs ``expected``
        (==, !=, <, <=, >, >=, contains, approx). Reads the live value via the runtime
        probe. Requires a play session + probe.
        """
        return await _assert_one(
            bridge,
            {"node_path": node_path, "property": property, "expected": expected, "op": op},
            timeout_ms,
        )

    @mcp.tool(meta=RUNTIME, tags=TESTING)
    async def run_test_scenario(
        scene: str = "",
        events: list[dict[str, Any]] | None = None,
        assertions: list[dict[str, Any]] | None = None,
        setup_ms: DelayMs = DEFAULT_TEST_SETUP_MS,
        settle_ms: DelayMs = DEFAULT_TEST_SETTLE_MS,
        stop_after: bool = True,
    ) -> ScenarioResult:
        """Run a play-test: play ``scene`` (or the main scene), wait ``setup_ms`` for the
        probe, play the ``events`` input sequence, wait ``settle_ms``, then evaluate each
        assertion (``{node_path, property, expected, op}``). Stops the run afterward
        unless ``stop_after`` is false. Returns per-assertion results and an overall pass.
        """
        await route(bridge, "cmd_play_scene", {"scene_path": scene})
        connected = await _wait_connected(bridge, setup_ms)
        if not connected:
            if stop_after:
                await route(bridge, "cmd_stop_scene", {})
            return ScenarioResult(
                passed=False,
                played=True,
                connected=False,
                error="runtime probe never connected (add the godot_mcp probe autoload).",
            )
        if events:
            await route(bridge, "cmd_play_input_sequence", {"events": events, "delay_ms": 16})
        await asyncio.sleep(settle_ms / 1000)
        results = [await _assert_one(bridge, spec, 1500) for spec in (assertions or [])]
        if stop_after:
            await route(bridge, "cmd_stop_scene", {})
        return ScenarioResult(
            passed=all(r.passed for r in results),
            played=True,
            connected=True,
            assertions=results,
        )

    @mcp.tool(meta=RUNTIME, tags=TESTING)
    async def run_stress_test(
        iterations: StressIterations = DEFAULT_STRESS_ITERATIONS,
        actions: list[str] | None = None,
        seed: int = 0,
        delay_ms: DelayMs = DEFAULT_STRESS_DELAY_MS,
    ) -> StressTestResult:
        """Fuzz the *running* game with ``iterations`` random input events drawn from
        ``actions`` (key names / input-map actions / "click"; a sensible default pool if
        omitted), ``seed`` for reproducibility. Reports whether the game survived (still
        playing afterward). Requires a play session + probe.
        """
        events = random_input_events(iterations, actions, seed)
        await route(bridge, "cmd_play_input_sequence", {"events": events, "delay_ms": delay_ms})
        # Give the sequence time to play out, then check the game is still alive.
        await asyncio.sleep(
            min(
                DEFAULT_STRESS_MAX_WAIT_SECONDS,
                iterations * delay_ms / 1000 + DEFAULT_STRESS_BUFFER_SECONDS,
            )
        )
        playing = bool((await route(bridge, "cmd_is_playing", {})).get("playing"))
        return StressTestResult(
            survived=playing, iterations=iterations, playing_after=playing, seed=seed
        )

    @mcp.tool(meta=READ_ONLY, tags=TESTING)
    async def compare_screenshots(
        image_a: str, image_b: str, tolerance: float = 0.0
    ) -> ScreenshotDiffResult:
        """Visually diff two base64 PNG screenshots (e.g. from ``capture_editor_screenshot``
        or saved baselines). ``tolerance`` (0..1) is the per-channel difference a pixel may
        have before it counts as different. Returns pixel/ratio diff metrics and ``match``.
        """
        try:
            return ScreenshotDiffResult(**compare_images(image_a, image_b, tolerance))
        except ImageCompareError as exc:
            raise ToolError(f"Could not compare images: {exc}") from exc
