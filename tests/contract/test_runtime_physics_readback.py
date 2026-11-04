"""Contract tests: runtime physics read-back (issue #599).

Godot 4.8 adds ``RigidBody2D/3D.get_velocity_at_position()`` /
``get_velocity_at_local_position()`` and the non-allocating
``PhysicsDirectSpaceState2D/3D.*_into()`` queries. They read the *running game*,
so they ride the #66 runtime-session rails (request_id + poll), and the addon
gates them on the 4.8 API with a structured ``UNSUPPORTED`` envelope.

Pinned here: the command names/params the server sends, the read-only/runtime
registration, the polling result shapes, and that ``UNSUPPORTED`` reaches the
client unchanged (no Python trace, no timeout).
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

VELOCITY_REPLY = {
    "ready": True,
    "node_path": "/root/Main/Body",
    "node_class": "RigidBody2D",
    "dimension": "2d",
    "local": False,
    "point": {"x": 10.0, "y": 20.0},
    "velocity": {"x": 0.0, "y": -9.8},
    "error": "",
}

QUERY_REPLY = {
    "ready": True,
    "method": "intersect_ray",
    "dimension": "2d",
    "hit": True,
    "count": 1,
    "results": [
        {
            "collider_path": "/root/Main/Wall",
            "collider_class": "StaticBody2D",
            "collider_id": 42,
            "collider_rid": 7,
            "shape": 0,
            "position": {"x": 1.0, "y": 2.0},
            "normal": {"x": 0.0, "y": -1.0},
            "face_index": -1,
        }
    ],
    "safe_fraction": None,
    "unsafe_fraction": None,
    "error": "",
}


class _ProbePeer:
    """Pending on the first poll for an id, ready afterwards (freshness pin)."""

    def __init__(self) -> None:
        self.polls: dict[str, int] = {}
        self.commands: list[CommandEnvelope] = []

    def responder(self, cmd: CommandEnvelope) -> ResponseEnvelope | None:
        self.commands.append(cmd)
        match cmd.command:
            case "cmd_get_velocity_at_point":
                return self._polled(cmd, VELOCITY_REPLY, "velocity_pending")
            case "cmd_physics_space_query":
                return self._polled(cmd, QUERY_REPLY, "query_pending")
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    def _polled(
        self, cmd: CommandEnvelope, ready: dict[str, object], reason: str
    ) -> ResponseEnvelope:
        rid = str(cmd.params.get("request_id", ""))
        self.polls[rid] = self.polls.get(rid, 0) + 1
        if self.polls[rid] < 2:
            return ResponseEnvelope.success(
                cmd.id, {"ready": False, "reason": reason, "request_id": rid}
            )
        return ResponseEnvelope.success(cmd.id, {**ready, "request_id": rid})


def _build(
    responder: object | None = None,
) -> tuple[FastMCP, FakeAddonConnection, _ProbePeer]:
    peer = _ProbePeer()
    conn = FakeAddonConnection(responder=responder or peer.responder)  # type: ignore[arg-type]
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn, peer


async def test_new_tools_are_read_only_and_gated_in_the_runtime_toolset() -> None:
    server, _, _ = _build()
    async with Client(server, mode="legacy") as client:
        assert "godot_runtime_get_velocity_at_point" not in {
            t.name for t in await client.list_tools()
        }
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        tools = {t.name: t for t in await client.list_tools()}
    names = {"godot_runtime_get_velocity_at_point", "godot_runtime_physics_space_query"}
    assert names <= set(tools)
    for name in names:
        tool = tools[name]
        assert tool.meta["safety_class"] == "read_only", name
        # read-only tools take no dry_run (safety-class contract).
        props = (tool.input_schema or {}).get("properties", {})
        assert "dry_run" not in props, name


async def test_get_velocity_at_point_polls_then_returns_the_live_vector() -> None:
    server, _, peer = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_get_velocity_at_point",
            {"node_path": "/root/Main/Body", "point": {"x": 10, "y": 20}},
        )
    sc = result.structured_content or {}
    assert sc["ready"] is True
    assert sc["node_class"] == "RigidBody2D"
    assert sc["dimension"] == "2d"
    assert sc["local"] is False
    assert sc["velocity"] == {"x": 0.0, "y": -9.8}
    sent = [c for c in peer.commands if c.command == "cmd_get_velocity_at_point"]
    assert len(sent) >= 2, "the tool must poll until the probe reply lands"
    params = sent[0].params
    assert params["node_path"] == "/root/Main/Body"
    assert params["point"] == {"x": 10, "y": 20}
    assert params["local"] is False
    assert params["request_id"], "a per-invocation request id is required (#670 pattern)"


async def test_get_velocity_at_point_local_variant_and_fresh_request_ids() -> None:
    server, _, peer = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        await client.call_tool(
            "godot_runtime_get_velocity_at_point",
            {"node_path": "/root/Main/Body", "point": {"x": 1, "y": 2}, "local": True},
        )
        await client.call_tool(
            "godot_runtime_get_velocity_at_point",
            {"node_path": "/root/Main/Body", "point": {"x": 1, "y": 2}, "local": True},
        )
    sent = [c for c in peer.commands if c.command == "cmd_get_velocity_at_point"]
    assert sent[0].params["local"] is True
    ids = {str(c.params["request_id"]) for c in sent}
    assert len(ids) == 2, f"each invocation must carry its own request id, got {ids}"


async def test_physics_space_query_returns_json_safe_hits() -> None:
    server, _, peer = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        result = await client.call_tool(
            "godot_runtime_physics_space_query",
            {
                "method": "intersect_ray",
                "dimension": "2d",
                "query": {"from": {"x": 0, "y": 0}, "to": {"x": 100, "y": 0}},
                "exclude": ["/root/Main/Player"],
                "max_results": 8,
            },
        )
    sc = result.structured_content or {}
    assert sc["ready"] is True and sc["hit"] is True and sc["count"] == 1
    hit = sc["results"][0]
    assert hit["collider_path"] == "/root/Main/Wall"
    assert hit["collider_id"] == 42
    assert hit["position"] == {"x": 1.0, "y": 2.0}
    sent = [c for c in peer.commands if c.command == "cmd_physics_space_query"]
    assert sent, "the tool must dispatch the query"
    params = sent[0].params
    assert params["method"] == "intersect_ray"
    assert params["dimension"] == "2d"
    assert params["query"] == {"from": {"x": 0, "y": 0}, "to": {"x": 100, "y": 0}}
    assert params["exclude"] == ["/root/Main/Player"]
    assert params["max_results"] == 8
    assert params["request_id"]


async def test_probe_read_errors_are_reported_in_band_not_as_shape_drift() -> None:
    """A probe-side error (bad node/query field) arrives as ``ready:true`` with an
    ``error`` string — the result model must accept the empty vector/payload
    defaults instead of rejecting them as shape drift (INTERNAL_ERROR)."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        rid = str(cmd.params.get("request_id", ""))
        if cmd.command == "cmd_get_velocity_at_point":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "node_path": "/root/Nope",
                    "node_class": "",
                    "dimension": "",
                    "local": False,
                    "point": {},
                    "velocity": {},
                    "error": "node not found at '/root/Nope'",
                    "request_id": rid,
                },
            )
        if cmd.command == "cmd_physics_space_query":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "ready": True,
                    "method": "intersect_ray",
                    "dimension": "2d",
                    "hit": False,
                    "count": 0,
                    "results": [],
                    "error": "unknown PhysicsRayQueryParameters2D field 'bogus'.",
                    "request_id": rid,
                },
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    server, _, _ = _build(responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        velocity = await client.call_tool(
            "godot_runtime_get_velocity_at_point",
            {"node_path": "/root/Nope", "point": {"x": 0, "y": 0}},
        )
        query = await client.call_tool(
            "godot_runtime_physics_space_query",
            {"method": "intersect_ray", "query": {"bogus": 1}},
        )
    assert velocity.structured_content["error"] == "node not found at '/root/Nope'"
    assert velocity.structured_content["point"] == {}
    assert velocity.structured_content["velocity"] == {}
    assert "bogus" in query.structured_content["error"]


async def test_godot_48_gate_surfaces_unsupported_unchanged() -> None:
    """The addon's 4.8 gate must come back as UNSUPPORTED + its actionable hint —
    an immediate structured error, never a bridge timeout or a Python trace."""

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command in {"cmd_get_velocity_at_point", "cmd_physics_space_query"}:
            return ResponseEnvelope.failure(
                cmd.id,
                "UNSUPPORTED",
                "get_velocity_at_position() requires Godot 4.8+ (this editor is 4.7.2-stable).",
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")

    server, _, _ = _build(responder)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "runtime"})
        velocity = await client.call_tool(
            "godot_runtime_get_velocity_at_point",
            {"node_path": "/root/Main/Body", "point": {"x": 0, "y": 0}},
            raise_on_error=False,
        )
        query = await client.call_tool(
            "godot_runtime_physics_space_query",
            {"method": "intersect_ray", "query": {"from": {"x": 0}, "to": {"x": 1}}},
            raise_on_error=False,
        )
    for result in (velocity, query):
        assert result.is_error
        text = str(result.content)
        assert "UNSUPPORTED" in text, text
        assert "4.8" in text, text
