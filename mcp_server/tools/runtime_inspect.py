"""Runtime inspection tools (issue #35).

Inspect a *running* game on the #66 runtime-session rails: watch a node property over
time and locate live UI (Control) elements. Requires a play session with the godot-mcp
runtime probe. All `read_only` against the live session, in the `runtime` toolset.
(``get_game_scene_tree`` — the third piece of #35 — already shipped with #66.)
"""

from __future__ import annotations

import uuid

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import RUNTIME_TAG
from mcp_server.constraints import Samples, TimeoutMs
from mcp_server.defaults import (
    DEFAULT_MONITOR_SAMPLES,
    DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS,
)
from mcp_server.models.runtime_inspect import (
    MonitorResult,
    PropertySamplesResult,
    ReadPropertyResult,
    UiElementsResult,
)
from mcp_server.safety import READ_ONLY, RUNTIME
from mcp_server.tools._route import poll_ready, route

RUNTIME_SET = {RUNTIME_TAG}


def register_runtime_inspect(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the runtime inspection tools."""

    @mcp.tool(meta=RUNTIME, tags=RUNTIME_SET)
    async def monitor_property(
        node_path: str,
        property: str,
        samples: Samples = DEFAULT_MONITOR_SAMPLES,
        on_change_only: bool = True,
        epsilon: float = 0.0001,
    ) -> MonitorResult:
        """Start watching ``property`` on the running game's node at ``node_path``
        (an absolute path from get_game_scene_tree). The probe captures ``samples``
        readings; collect them with get_property_samples. ``on_change_only`` (default)
        queues a sample only when the value changed (float ``epsilon``-tolerant, also
        inside Vector2/3), so a static property yields fewer deduped entries.

        ``runtime``: starting the monitor is a side effect on the play session.
        Requires a play session + runtime probe; for a single current value use
        read_property instead.
        """
        params = {
            "node_path": node_path,
            "property": property,
            "samples": samples,
            "on_change_only": on_change_only,
            "epsilon": epsilon,
        }
        return MonitorResult(**await route(bridge, "cmd_monitor_property", params))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def get_property_samples() -> PropertySamplesResult:
        """Return the time series captured by the most recent ``monitor_property``:
        ``samples`` is ``[{frame, value}]`` (``ready=false`` until the capture completes;
        ``error`` set if the node/property was invalid).
        """
        return PropertySamplesResult(**await route(bridge, "cmd_get_property_samples", {}))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def read_property(
        node_path: str,
        property: str,
        timeout_ms: TimeoutMs = DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS,
    ) -> ReadPropertyResult:
        """Read a property from the running game's node at ``node_path`` ONCE and
        return its current value (JSON-coerced, same shapes ``monitor_property``
        samples use). The dedicated #571 one-shot path: it never touches the
        ``monitor_property`` capture slot, so an assert or read during a running
        capture cannot replace that capture's series. Requires a play session +
        runtime probe.

        WHEN TO USE: a single current-value check (assertions, "what is X now?").
        WHEN NOT TO USE: you want a series over time — use ``monitor_property`` +
        ``get_property_samples``.
        """
        params = {
            "node_path": node_path,
            "property": property,
            # Stable per-invocation id (constant across the poll loop) so a reply is
            # never confused with a prior request's stale result (#571, find_ui pattern).
            "request_id": uuid.uuid4().hex,
        }
        result = await poll_ready(bridge, "cmd_read_property", params, timeout_ms)
        return ReadPropertyResult(**result)

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def find_ui_elements(
        name_contains: str = "",
        class_filter: str = "",
        visible_only: bool = False,
        timeout_ms: TimeoutMs = DEFAULT_RUNTIME_INSPECT_TIMEOUT_MS,
    ) -> UiElementsResult:
        """Locate live UI (Control) nodes in the running game, each with its path, class,
        visibility, global ``rect`` (use it with ``simulate_mouse`` to click), and ``text``
        if any. Filter by ``name_contains`` / ``class_filter`` (e.g. "Button") /
        ``visible_only``. Requires a play session + runtime probe.
        """
        params = {
            "name_contains": name_contains,
            "class_filter": class_filter,
            "visible_only": visible_only,
            # Stable per-invocation id (constant across the poll loop) so the addon scans
            # once and we never match a prior identical-filter request's stale result.
            "request_id": uuid.uuid4().hex,
        }
        # The probe answers asynchronously; poll the addon's cache (which dispatches one
        # scan for this request_id) until it reflects this request or timeout_ms elapses.
        result = await poll_ready(bridge, "cmd_find_ui_elements", params, timeout_ms)
        return UiElementsResult(**result)
