"""Contract tests: result-model ValidationError surfaces as INTERNAL_ERROR (#567).

When a tool builds its typed result from an addon payload and the payload
doesn't match the model (``ClassInfo(**result)`` with a mismatched field type),
pydantic's ``ValidationError`` escaped the tool body and FastMCP masked it as
JSON-RPC ``-32602 Invalid request parameters`` — with none of pydantic's
per-field detail on the wire, pointing the agent at its own (correct) arguments.

Contract:
- A result-shape mismatch surfaces as a ``ToolError`` whose text carries
  ``INTERNAL_ERROR`` plus the model name, field paths, and inputs — clearly
  framed as "the addon payload didn't match", not "you sent bad params".
- Request-side parameter validation is untouched: it keeps its detailed error
  and never claims INTERNAL_ERROR (``-32602`` stays reserved for it).
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.contract.test_describe_class import NODE2D, _class_responder
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_result_shape_mismatch_raises_internal_error_with_field_detail() -> None:
    """The #567 repro: the addon sends a payload the result model rejects.

    Before the fix the client saw ``MCPError: Invalid request parameters``
    (opaque -32602); after, a structured ToolError naming the field.
    """
    broken = dict(NODE2D)
    broken["can_instantiate"] = 42  # bool field, non-coercible int from the addon
    conn = FakeAddonConnection(responder=_class_responder(broken, ["Node2D"]))
    async with Client(_build(conn)) as client:
        result = await client.call_tool(
            "godot_describe_class", {"class_name": "Node2D"}, raise_on_error=False
        )
    assert result.is_error, "a result-shape mismatch must be an error result"
    text = str(result.content)
    assert "INTERNAL_ERROR" in text, text
    assert "can_instantiate" in text, f"field path missing from: {text}"
    assert "ClassInfo" in text, f"result model name missing from: {text}"
    assert "42" in text, f"offending input missing from: {text}"
    # The framing must point at the payload, not the caller's arguments.
    assert "arguments" in text.lower(), text


async def test_result_shape_mismatch_never_masks_as_invalid_request_parameters() -> None:
    """The wire error must not read as the caller's fault (-32602 framing)."""
    broken = dict(NODE2D)
    broken["inherits"] = 42  # str field, int payload
    conn = FakeAddonConnection(responder=_class_responder(broken, ["Node2D"]))
    async with Client(_build(conn)) as client:
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("godot_describe_class", {"class_name": "Node2D"})
    assert "Invalid request parameters" not in str(exc_info.value), exc_info.value
    assert "INTERNAL_ERROR" in str(exc_info.value), exc_info.value


async def test_request_side_validation_error_is_untouched() -> None:
    """A genuinely bad REQUEST param keeps the request-validation error detail
    and never claims INTERNAL_ERROR — -32602 stays reserved for it (#567)."""
    conn = FakeAddonConnection(responder=_class_responder(NODE2D, ["Node2D"]))
    async with Client(_build(conn)) as client:
        result = await client.call_tool(
            "godot_describe_class",
            {"class_name": "Node2D", "include_inherited": "not-a-bool"},
            raise_on_error=False,
        )
    assert result.is_error
    text = str(result.content)
    assert "INTERNAL_ERROR" not in text, text
    assert "include_inherited" in text, text