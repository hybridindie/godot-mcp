"""Contract tests for ``outputSchema`` / ``structuredContent`` (issue #385).

The MCP 2025-11-25 spec lets a tool declare an ``outputSchema`` (JSON Schema
2020-12) and return ``structuredContent`` — machine-parsed JSON — with the
text content kept as a serialized fallback. FastMCP 4.0 auto-derives both from
the Pydantic return annotation, so the contract here pins three things:

1. **Declaration**: every tool declares a non-degenerate ``outputSchema`` —
   one exception, the editor screenshot tool, returns ``ImageContent`` (non-JSON
   content gets no ``structuredContent`` per spec, so no schema is correct).
2. **Consistency, both directions** (spec best practice): for the high-traffic
   tools, the emitted ``structuredContent`` *validates* against the declared
   schema, and the text fallback is the faithful JSON serialization of the same
   object — existing clients that parse text stay unbroken.
3. **No regressions from tool transforms**: schemas must survive the
   ``godot_`` renaming transform and toolset gating (checked implicitly — the
   client-facing names below are the post-transform public names).

A degenerate schema — ``{type: object, additionalProperties: true}`` with no
``properties`` — is useless to a client and fails assertion 1. ``godot_undo``
degenerated exactly this way (its ``@model_serializer`` hides fields from
pydantic's serialization-mode schema generation), which is why it is fixed via
an explicit ``output_schema=UndoResult.model_json_schema()``.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.providers.base import Provider
from jsonschema import Draft202012Validator

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio

# The one tool whose content is an image, not JSON: the spec says structured
# content applies to JSON results, so this tool correctly declares no schema.
# Keyed by the original handler name — Provider.list_tools (all tools, gated
# included) yields pre-transform names; the public client name is
# godot_editor_capture_screenshot.
IMAGE_TOOLS = {"capture_editor_screenshot"}


def image_responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    if cmd.command == "cmd_capture_editor_screenshot":
        png = base64.b64encode(b"\x89PNG-fake").decode()
        return ResponseEnvelope.success(cmd.id, {"base64": png, "format": "image/png"})
    return None


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    """Canned addon answers for the high-traffic tools' bridge commands."""
    p = cmd.params
    match cmd.command:
        case "cmd_get_project_info":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "name": "demo",
                    "godot_version": "4.7",
                    "main_scene": "res://main.tscn",
                    "autoloads": {"Game": "res://game.gd"},
                    "input_actions": ["jump"],
                },
            )
        case "cmd_get_scene_tree":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "tree": {
                        "name": "Main",
                        "type": "Node2D",
                        "path": ".",
                        "script": None,
                        "children": [
                            {
                                "name": "Player",
                                "type": "CharacterBody2D",
                                "path": "Player",
                                "script": None,
                                "children": [],
                            }
                        ],
                    }
                },
            )
        case "cmd_get_node_properties":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p["node_path"],
                    "type": "Sprite2D",
                    "script": "res://player.gd",
                    "properties": {"speed": 200.0},
                    "children": ["Sprite2D"],
                },
            )
        case "cmd_list_scripts":
            return ResponseEnvelope.success(
                cmd.id,
                {"directory": p.get("directory", "res://"), "scripts": ["res://a.gd"]},
            )
        case "cmd_get_script_for_node":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "node_path": p.get("node_path") or "",
                    "script_path": "res://player.gd",
                    "content": "extends Node\n",
                },
            )
        case "cmd_undo":
            return ResponseEnvelope.success(
                cmd.id,
                {"undone": 1, "requested": p.get("count", 1), "last_action": "Create Node"},
            )
    return None  # bootstrap commands (cmd_ping/…) auto-answered by the fake


class _FakeRunner:
    """Runner double for godot_runtime_run_and_capture (no real Godot)."""

    binary: str | None = "fake-godot"

    async def run(
        self, project_dir: str, scene: str | None, timeout: float
    ) -> RunOutput:
        return RunOutput(command=["fake"], exit_code=0, stdout="hello\n", stderr="")

    async def check_script(
        self, project_dir: str, script_path: str, timeout: float
    ) -> RunOutput:
        return RunOutput(command=["fake"])

    async def export(
        self, project_dir: str, preset: str, output_path: str, debug: bool, timeout: float
    ) -> RunOutput:
        return RunOutput(command=["fake"])

    async def run_tests(
        self, project_dir: str, test_dir: str, timeout: float
    ) -> RunOutput:
        return RunOutput(command=["fake"])


async def _build() -> FastMCP:
    conn = FakeAddonConnection(responder=_responder)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    return create_server(config, bridge=bridge, runner=_FakeRunner())


async def test_every_tool_declares_a_non_degenerate_output_schema() -> None:
    """Whole surface (180 tools, gated included) declares a useful schema.

    A schema with no ``properties`` (e.g. bare ``{additionalProperties: true}``)
    is degenerate: a client can't type-check the result. The one allowed
    exception is the image-capture tool — non-JSON content, spec-correct
    without a schema.
    """
    server = await _build()
    tools = await Provider.list_tools(server)
    assert tools, "no tools registered"

    offenders: list[str] = []
    for tool in tools:
        if tool.name in IMAGE_TOOLS:
            assert tool.output_schema is None, (
                f"{tool.name} returns ImageContent — it must not declare a schema"
            )
            continue
        schema = tool.output_schema
        if schema is None:
            offenders.append(f"{tool.name}: no outputSchema")
        elif not isinstance(schema.get("properties"), dict) or not schema["properties"]:
            offenders.append(f"{tool.name}: degenerate schema {schema}")
    assert not offenders, "\n".join(sorted(offenders))


async def test_high_traffic_tools_emit_schema_consistent_structured_content() -> None:
    """Both directions, per the issue's acceptance criteria.

    Direction one: the emitted ``structuredContent`` validates against the
    declared ``outputSchema`` (Draft 2020-12 — the version the spec names).
    Direction two: the text fallback is the faithful serialization of the same
    object, so text-parsing clients (godot-agents' MCPResult today) are
    unbroken and see identical data.
    """
    calls: dict[str, dict[str, Any]] = {
        "godot_inspection_get_project_info": {},
        "godot_inspection_get_scene_tree": {"max_depth": 2},
        "godot_inspection_get_node_properties": {"node_path": "Player"},
        "godot_scripts_list": {},
        "godot_scripts_get_for_node": {},
        "godot_runtime_run_and_capture": {},
        "godot_undo": {},
    }
    server = await _build()
    async with Client(server) as client:
        for category in ("scripts", "runtime"):
            await client.call_tool("godot_enable_toolset", {"category": category})
        tools = {t.name: t for t in await client.list_tools()}
        for name, args in calls.items():
            tool = tools[name]
            assert tool.output_schema is not None, f"{name} declares no outputSchema"
            result = await client.call_tool(name, args)
            # Direction one: schema validates the structured content.
            assert result.structured_content is not None, f"{name} emitted no structuredContent"
            errors = sorted(
                Draft202012Validator(tool.output_schema).iter_errors(
                    result.structured_content
                ),
                key=str,
            )
            assert not errors, f"{name}: " + "; ".join(e.message for e in errors)
            # Direction two: text is the faithful fallback of the same object.
            text = result.content[0].text
            assert json.loads(text) == result.structured_content, f"{name}: text/structured drift"


def _loads(text: str) -> Any:
    import json

    return json.loads(text)


async def test_image_tool_emits_content_without_structured_content() -> None:
    """The spec exception: an image result carries ImageContent, no JSON."""
    conn = FakeAddonConnection(responder=image_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "editor"})
        result = await client.call_tool("godot_editor_capture_screenshot", {})
    assert result.structured_content is None
    types = [type(c).__name__ for c in result.content]
    assert "ImageContent" in types, f"expected image content, got {types}"