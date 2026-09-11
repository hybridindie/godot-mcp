"""Editor screenshot tool (issue #33).

Returns a screenshot of the editor viewport as image content so vision-capable
agents can *see* the result of a change. Read-only; gated `editor` toolset. The
addon defers the viewport read-back one rendered frame (an inline ``get_image``
can stall the router's main thread on some display servers) and the server
polls until the capture is ready; this decodes the base64 PNG into a FastMCP
``Image`` so the client receives an image block.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from mcp_server.bridge import Bridge
from mcp_server.categories import EDITOR_TAG
from mcp_server.constraints import TimeoutMs
from mcp_server.defaults import DEFAULT_CAPTURE_TIMEOUT_MS, DEFAULT_POLL_INTERVAL_SECONDS
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import route


def register_editor(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the editor screenshot tool."""

    @mcp.tool(meta=READ_ONLY, tags={EDITOR_TAG})
    async def capture_editor_screenshot(
        timeout_ms: TimeoutMs = DEFAULT_CAPTURE_TIMEOUT_MS,
    ) -> Image:
        """Capture the Godot editor's main viewport and return it as a PNG image, so
        you can visually inspect the current editor state. Read-only. The capture is
        taken on the next rendered editor frame; if the editor is fully occluded or
        not redrawing, the poll expires with an error.
        """
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
        result: dict[str, Any] = {}
        reason = ""
        while True:
            result = await route(bridge, "cmd_capture_editor_screenshot")
            # Done when a payload arrived (``ready`` truthy or a base64 body from
            # an older addon); ``{"ready": false}`` means "grab still pending".
            if result.get("base64") or result.get("ready"):
                break
            # #416/#456: the addon self-reports why the editor isn't cooperating
            # (e.g. "editor_not_drawing") — keep it for the expiry error so the
            # agent gets the actual cause, not the bridge's generic timeout text.
            reason = str(result.get("reason", "")).strip()
            if asyncio.get_event_loop().time() >= deadline:
                hint = (
                    f" — addon reason: '{reason}' (editor viewport not rendering; "
                    "occluded or minimized editor?)"
                    if reason
                    else " — is the editor window rendering (not fully hidden/minimized)?"
                )
                raise ToolError(
                    f"Editor viewport capture did not complete within {timeout_ms}ms{hint}"
                )
            await asyncio.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
        if not result.get("base64"):
            reason = str(result.get("error", "")).strip()
            detail = f" ({reason})" if reason else ""
            raise ToolError(f"Screenshot capture returned no image data.{detail}")
        try:
            data = base64.b64decode(result["base64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"Screenshot data was not valid base64: {exc}") from exc
        # Normalize e.g. "image/png" → "png".
        fmt = str(result.get("format", "png")).removeprefix("image/")
        return Image(data=data, format=fmt)
