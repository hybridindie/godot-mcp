"""Runtime inspection tools (issue #35).

Inspect a *running* game on the #66 runtime-session rails: watch a node property over
time and locate live UI (Control) elements. Requires a play session with the godot-mcp
runtime probe. All `read_only` against the live session, in the `runtime` toolset.
(``get_game_scene_tree`` — the third piece of #35 — already shipped with #66.)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import RUNTIME_TAG
from mcp_server.models.runtime_inspect import (
    MonitorResult,
    PropertySamplesResult,
    UiElementsResult,
)
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import route

RUNTIME_SET = {RUNTIME_TAG}


def register_runtime_inspect(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the runtime inspection tools."""

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def monitor_property(node_path: str, property: str, samples: int = 30) -> MonitorResult:
        """Start watching ``property`` on the running game's node at ``node_path`` (an
        absolute path from ``get_game_scene_tree``, e.g. "/root/Main/Player"). The probe
        captures ``samples`` readings, one per frame; collect them with
        ``get_property_samples``. Requires a play session + runtime probe.
        """
        params = {"node_path": node_path, "property": property, "samples": samples}
        return MonitorResult(**await route(bridge, "cmd_monitor_property", params))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def get_property_samples() -> PropertySamplesResult:
        """Return the time series captured by the most recent ``monitor_property``:
        ``samples`` is ``[{frame, value}]`` (``ready=false`` until the capture completes;
        ``error`` set if the node/property was invalid).
        """
        return PropertySamplesResult(**await route(bridge, "cmd_get_property_samples", {}))

    @mcp.tool(meta=READ_ONLY, tags=RUNTIME_SET)
    async def find_ui_elements(
        name_contains: str = "",
        class_filter: str = "",
        visible_only: bool = False,
        timeout_ms: int = 2000,
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
        # The probe answers asynchronously; poll the addon's cache until it reflects this
        # request (or the timeout elapses). Bounded, ~100ms cadence.
        attempts = max(1, timeout_ms // 100)
        result: dict[str, Any] = {"ready": False, "elements": []}
        for _ in range(attempts):
            result = await route(bridge, "cmd_find_ui_elements", params)
            if result.get("ready"):
                break
            await asyncio.sleep(0.1)
        return UiElementsResult(**result)
