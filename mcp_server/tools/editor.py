"""Editor screenshot tool (issue #33).

Returns a screenshot of the editor viewport as image content so vision-capable
agents can *see* the result of a change. Read-only; gated `editor` toolset. The
addon captures the viewport and returns a base64 PNG; this decodes it into a
FastMCP ``Image`` so the client receives an image block.
"""

from __future__ import annotations

import base64
import binascii

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from mcp_server.bridge import Bridge
from mcp_server.categories import EDITOR_TAG
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import route


def register_editor(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the editor screenshot tool."""

    @mcp.tool(meta=READ_ONLY, tags={EDITOR_TAG})
    async def capture_editor_screenshot() -> Image:
        """Capture the Godot editor's main viewport and return it as a PNG image, so
        you can visually inspect the current editor state. Read-only.
        """
        result = await route(bridge, "cmd_capture_editor_screenshot")
        encoded = result.get("base64")
        if not encoded:
            raise ToolError("Screenshot capture returned no image data.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"Screenshot data was not valid base64: {exc}") from exc
        # Normalize e.g. "image/png" → "png".
        fmt = str(result.get("format", "png")).removeprefix("image/")
        return Image(data=data, format=fmt)
