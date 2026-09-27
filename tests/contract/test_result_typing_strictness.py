"""Contract tests: addon-produced result models reject cross-type payloads (#580).

The #567 middleware (``ResultValidationMiddleware``) turns hard shape mismatches
into actionable INTERNAL_ERRORs — but pydantic's *lax* mode silently coerces
part of the drift, which never reaches it:

- ``bool`` fields accept ``"yes"``/``"1"``/ints (a string or int addon payload
  becomes a plausible ``True`` on the wire);
- ``int`` fields accept floats with a zero fraction (``1.0`` → ``1``).

The addon produces these fields via GDScript typed producers (GDScript bools,
ints, strings → JSON booleans/numbers/strings), so a cross-type payload is
genuine shape drift and must fail loudly instead of coercing. Deliberate
exceptions: ``Any``-typed fields (``value``/``expected``/``default`` — the
Variant shapes from #564) and stringified-argument repair stay lax.

Contract:
- a shared JSON-strict type module exists (``mcp_server.models.json_strict``);
- the targeted result models (probe surfaces, class_info, mutation) validate
  their typed fields strictly: cross-type payloads raise — and, riding the
  #567 middleware, surface as INTERNAL_ERROR on the wire;
- numeric widening the addon genuinely produces (int → float) stays allowed.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.contract.test_describe_class import NODE2D, _class_responder
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

READ_REPLY = {
    "ready": True,
    "node_path": "/root/Scene/Body",
    "property": "global_position",
    "value": {"x": 1.0, "y": 2.0, "z": 3.0},
    "error": "",
}


def _build_with_read(
    payload: dict[str, Any],
) -> tuple[FastMCP, FakeAddonConnection]:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_read_property":
            return ResponseEnvelope.success(cmd.id, payload)
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def _read_property(
    server: FastMCP, expect_error: bool = True
) -> CallToolResult:
    """Call godot_runtime_read_property with the runtime toolset enabled."""
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_read_property",
            {"node_path": "/root/Scene/Body", "property": "global_position"},
            raise_on_error=not expect_error,
        )
        return result  # type: ignore[no-any-return]  # client return is Any-typed


async def test_read_property_bool_from_string_is_internal_error() -> None:
    """The addon sends ``ready: "yes"`` — shape drift, must surface as
    INTERNAL_ERROR (via #567), not coerce to True."""
    payload = {**READ_REPLY, "ready": "yes"}
    server, _ = _build_with_read(payload)
    result = await _read_property(server)
    assert result.is_error
    text = str(result.content)
    assert "INTERNAL_ERROR" in text, text
    assert "ready" in text, text


async def test_read_property_int_from_bool_fails() -> None:
    """A bool payload where the model declares int (frame counters etc.) fails."""
    payload = {**READ_REPLY, "ready": 1}
    server, _ = _build_with_read(payload)
    result = await _read_property(server)
    assert result.is_error
    assert "INTERNAL_ERROR" in str(result.content)


async def test_monitor_result_bool_from_string_is_internal_error() -> None:
    server, conn = _build_with_read(READ_REPLY)

    def with_monitor(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_monitor_property":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "monitoring": "yes",
                    "node_path": cmd.params["node_path"],
                    "property": cmd.params["property"],
                },
            )
        if cmd.command == "cmd_read_property":
            return ResponseEnvelope.success(cmd.id, READ_REPLY)
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    conn._responder = with_monitor
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_monitor_property",
            {"node_path": "/root/Scene/Body", "property": "position"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "INTERNAL_ERROR" in str(result.content)


async def test_describe_class_bool_from_string_is_internal_error() -> None:
    broken = dict(NODE2D)
    broken["can_instantiate"] = "yes"  # coerced to True in lax mode (#580)
    conn = FakeAddonConnection(responder=_class_responder(broken, ["Node2D"]))
    async with Client(
        create_server(
            ServerConfig(), bridge=Bridge(ServerConfig().bridge, connector=connector_for(conn))
        )
    ) as client:
        result = await client.call_tool(
            "godot_describe_class", {"class_name": "Node2D"}, raise_on_error=False
        )
    assert result.is_error
    text = str(result.content)
    assert "INTERNAL_ERROR" in text, text
    assert "can_instantiate" in text


# --- lax-by-design fields stay lax -------------------------------------------


async def test_any_typed_value_field_still_accepts_the_addon_variants() -> None:
    """`value: Any` (ReadPropertyResult) carries #564 Variant shapes — lax by
    design; a string value is a legitimate property value, not drift."""
    payload = {**READ_REPLY, "value": "a string value"}
    server, _ = _build_with_read(payload)
    result = await _read_property(server, expect_error=False)
    structured = result.structured_content or {}
    assert structured["value"] == "a string value"


# --- unit: numeric widening the addon genuinely produces stays allowed -------


def test_json_strict_float_still_accepts_int_widening() -> None:
    from pydantic import BaseModel, ValidationError

    from mcp_server.models.json_strict import JSONFloat

    class M(BaseModel):
        f: JSONFloat

    assert M(f=3).f == 3.0  # GDScript int → JSON number → float field
    with pytest.raises(ValidationError):
        M(f="3")  # type: ignore[arg-type]  # a string payload is drift


def test_json_strict_bool_rejects_everything_but_real_bools() -> None:
    from pydantic import BaseModel, ValidationError

    from mcp_server.models.json_strict import JSONBool

    class M(BaseModel):
        b: JSONBool

    assert M(b=True).b is True
    for bad in ("yes", "1", 1, 0, "False"):
        with pytest.raises(ValidationError):
            M(b=bad)  # type: ignore[arg-type]  # cross-type payloads are the point