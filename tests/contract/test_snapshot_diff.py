"""Contract tests for snapshot + diff subtree tools (issue #535).

Drive the real FastMCP server over the in-memory client, backed by a fake addon
peer: snapshot returns a stable snapshot_id + tree; diff compares two snapshot
ids (or snapshot + live re-read) into added/removed/changed; the server-side
store is bounded (LRU) and snapshots are JSON-safe and depth-capped.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.models.inspection import DiffEntry, SnapshotDiff
from mcp_server.server import create_server
from mcp_server.snapshots import SnapshotStore
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# A tiny serialized subtree the fake addon returns for cmd_snapshot_subtree.
_TREE = {
    "name": "Main",
    "type": "Node2D",
    "path": ".",
    "script": None,
    "properties": {"speed": 200.0, "position": {"x": 0.0, "y": 0.0}},
    "groups": [],
    "children": [
        {
            "name": "Player",
            "type": "CharacterBody2D",
            "path": "Player",
            "script": "res://player.gd",
            "properties": {"speed": 200.0, "position": {"x": 5.0, "y": 6.0}},
            "groups": ["enemies"],
            "children": [],
        }
    ],
}


def _snapshot_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_snapshot_subtree":
        if cmd.params.get("node_path") == "Missing":
            return ResponseEnvelope.failure(
                cmd.id, "RESOURCE_NOT_FOUND", "No node at 'Missing'."
            )
        return ResponseEnvelope.success(
            cmd.id, {"node_path": cmd.params.get("node_path", "."), "snapshot": _TREE}
        )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_snapshot_subtree_routes_and_returns_id() -> None:
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        result = await client.call_tool(
            "godot_inspection_snapshot_subtree",
            {"node_path": "Player", "properties": ["speed"]},
        )
    data = result.structured_content
    assert data["node_path"] == "Player"
    assert data["snapshot_id"], "snapshot must return a referenceable id"
    assert data["snapshot"]["name"] == "Main"
    # The requested property filter rides through to the addon.
    cmd = conn.last_command()
    assert cmd.command == "cmd_snapshot_subtree"
    assert cmd.params["node_path"] == "Player"
    assert cmd.params["properties"] == ["speed"]


async def test_snapshot_subtree_defaults() -> None:
    # Defaults: whole scene ("."), all properties.
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        await client.call_tool("godot_inspection_snapshot_subtree", {})
    cmd = conn.last_command()
    assert cmd.params["node_path"] == "."
    assert cmd.params["properties"] == []
    assert cmd.params["max_depth"] == -1


async def test_snapshot_subtree_missing_node_is_structured_error() -> None:
    async with Client(_build(FakeAddonConnection(responder=_snapshot_responder))) as client:
        result = await client.call_tool(
            "godot_inspection_snapshot_subtree",
            {"node_path": "Missing"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_snapshot_ids_stable_and_distinct() -> None:
    # Two snapshots of the same tree: ids are stable (referenceable) and unique.
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        first = await client.call_tool("godot_inspection_snapshot_subtree", {})
        second = await client.call_tool("godot_inspection_snapshot_subtree", {})
    id_a = first.structured_content["snapshot_id"]
    id_b = second.structured_content["snapshot_id"]
    assert id_a != id_b
    assert id_a == "s1"
    assert id_b == "s2"


async def test_snapshot_default_captures_transform_and_groups() -> None:
    # #535 ticket wording: "groups, transforms" are part of the snapshot shape —
    # the addon captures them per node (transforms only where the class exposes them).
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_inspection_snapshot_subtree", {})
    player = result.structured_content["snapshot"]["children"][0]
    assert player["properties"]["position"] == {"x": 5.0, "y": 6.0}
    assert player["groups"] == ["enemies"]
    assert result.structured_content["snapshot"]["groups"] == []


async def test_diff_reports_group_changes() -> None:
    # Groups are part of the snapshot shape, so a membership change between two
    # snapshots shows up as a changed entry (property "groups").
    before: dict[str, Any] = {
        "name": "Main",
        "type": "Node2D",
        "path": ".",
        "script": None,
        "properties": {},
        "groups": [],
        "children": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "path": "Player",
                "script": None,
                "properties": {},
                "groups": ["enemies"],
                "children": [],
            }
        ],
    }
    after: dict[str, Any] = {
        "name": "Main",
        "type": "Node2D",
        "path": ".",
        "script": None,
        "properties": {},
        "groups": [],
        "children": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "path": "Player",
                "script": None,
                "properties": {},
                "groups": ["enemies", "spawnable"],
                "children": [],
            }
        ],
    }
    store = SnapshotStore()
    id_before = store.put(before)
    id_after = store.put(after)
    # Diff through the pure helper the tool delegates to.
    from mcp_server.tools.inspection import diff_trees

    diff = diff_trees(store.get(id_before) or before, store.get(id_after) or after)
    result = SnapshotDiff(
        added=diff["added"],
        removed=diff["removed"],
        changed=[DiffEntry(**e) for e in diff["changed"]],
    )
    assert result.changed == [
        DiffEntry(
            node="Player", property="groups", before=["enemies"], after=["enemies", "spawnable"]
        )
    ]


async def test_diff_two_snapshots_reports_changed() -> None:
    # Snapshot s1 (speed=200), then a changed tree under s2 (speed=900).
    changed = {
        "name": "Main",
        "type": "Node2D",
        "path": ".",
        "script": None,
        "properties": {"speed": 200.0, "position": {"x": 0.0, "y": 0.0}},
        "groups": [],
        "children": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "path": "Player",
                "script": "res://player.gd",
                "properties": {"speed": 900.0, "position": {"x": 5.0, "y": 6.0}},
                "groups": ["enemies"],
                "children": [],
            }
        ],
    }
    calls: list[str] = []

    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        calls.append(cmd.command)
        if cmd.command == "cmd_snapshot_subtree":
            tree = changed if len([c for c in calls if c == "cmd_snapshot_subtree"]) > 1 else _TREE
            return ResponseEnvelope.success(
                cmd.id, {"node_path": cmd.params.get("node_path", "."), "snapshot": tree}
            )
        return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected command")

    async with Client(_build(FakeAddonConnection(responder=responder))) as client:
        await client.call_tool("godot_inspection_snapshot_subtree", {})
        await client.call_tool("godot_inspection_snapshot_subtree", {})
        result = await client.call_tool(
            "godot_inspection_diff_snapshots", {"before_id": "s1", "after_id": "s2"}
        )
    data = result.structured_content
    assert data["added"] == []
    assert data["removed"] == []
    changed_entries = data["changed"]
    assert len(changed_entries) == 1
    entry = changed_entries[0]
    assert entry["node"] == "Player"
    assert entry["property"] == "speed"
    assert entry["before"] == 200.0
    assert entry["after"] == 900.0
    # A pure diff must not round-trip the bridge.
    assert calls.count("cmd_snapshot_subtree") == 2


async def test_diff_identical_snapshots_is_empty() -> None:
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        await client.call_tool("godot_inspection_snapshot_subtree", {})
        result = await client.call_tool(
            "godot_inspection_diff_snapshots", {"before_id": "s1", "after_id": "s1"}
        )
    data = result.structured_content
    assert data == {"added": [], "removed": [], "changed": []}


async def test_diff_snapshot_vs_live_rereads_bridge() -> None:
    # after_id=None: the tool re-reads the same path live (a second bridge call).
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        await client.call_tool("godot_inspection_snapshot_subtree", {"node_path": "Player"})
        await client.call_tool(
            "godot_inspection_diff_snapshots", {"before_id": "s1", "node_path": "Player"}
        )
    assert sum("cmd_snapshot_subtree" in msg for msg in conn.sent) == 2


async def test_diff_unknown_snapshot_id_is_structured_error() -> None:
    conn = FakeAddonConnection(responder=_snapshot_responder)
    async with Client(_build(conn)) as client:
        await client.call_tool("godot_inspection_snapshot_subtree", {})
        result = await client.call_tool(
            "godot_inspection_diff_snapshots", {"before_id": "nope", "after_id": "s1"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)


async def test_diff_snapshots_rejects_batch_entry() -> None:
    # diff_snapshots is a server-side op: a run_commands/batch entry must get a
    # targeted refusal, not diff params sent to the addon as bridge params.
    from fastmcp.exceptions import ToolError

    from mcp_server.command_map import resolve_command

    with pytest.raises(ToolError) as exc:
        resolve_command("inspection_diff_snapshots")
    assert "directly" in str(exc.value)


async def test_snapshot_store_is_bounded() -> None:
    # The LRU store evicts its oldest entry beyond the bound — server memory
    # stays capped no matter how many snapshots an agent takes (issue #535).
    store = SnapshotStore(max_entries=2)
    store.put({"v": 1})
    store.put({"v": 2})
    store.put({"v": 3})
    assert store.get("s1") is None
    assert store.get("s2") == {"v": 2}
    assert store.get("s3") == {"v": 3}


async def test_snapshot_tools_are_read_only() -> None:
    async with Client(_build(FakeAddonConnection(responder=_snapshot_responder))) as client:
        tools = await client.list_tools()
    by_name = {t.name: t for t in tools}
    for name in (
        "godot_inspection_snapshot_subtree",
        "godot_inspection_diff_snapshots",
    ):
        assert by_name[name].meta is not None
        assert by_name[name].meta.get("safety_class") == "read_only"