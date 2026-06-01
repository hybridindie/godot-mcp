"""Contract tests for the script read/patch tools (issue #10).

In-memory client + fake addon peer + injected fake runner (for parse checks).
"""

from __future__ import annotations

from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.runtime import RunOutput
from mcp_server.server import create_server
from mcp_server.tools.scripts import parse_check_errors
from tests.fakes import FakeAddonConnection, connector_for

# asyncio_mode=auto runs the async tests; no module-wide mark (it would warn on the
# synchronous parser test below).


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_read_script":
            if p.get("script_path") == "res://missing.gd":
                return ResponseEnvelope.failure(cmd.id, "RESOURCE_NOT_FOUND", "No script.")
            return ResponseEnvelope.success(
                cmd.id, {"script_path": p["script_path"], "content": "extends Node\n"}
            )
        case "cmd_list_scripts":
            return ResponseEnvelope.success(
                cmd.id, {"directory": p["directory"], "scripts": ["res://a.gd", "res://b.gd"]}
            )
        case "cmd_get_script_for_node":
            return ResponseEnvelope.success(
                cmd.id, {"node_path": p["node_path"], "script_path": None, "content": None}
            )
        case "cmd_write_script":
            return ResponseEnvelope.success(
                cmd.id, {"script_path": p["script_path"], "created": True}
            )
        case "cmd_patch_script":
            return ResponseEnvelope.success(
                cmd.id, {"script_path": p["script_path"], "replacements": 2}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


class _FakeRunner:
    binary: str | None = "fake-godot"

    def __init__(self, check_output: RunOutput) -> None:
        self._check = check_output

    async def run(self, project_dir: str, scene: str | None, timeout: float) -> RunOutput:
        return RunOutput(command=["fake"])

    async def check_script(self, project_dir: str, script_path: str, timeout: float) -> RunOutput:
        return self._check


def _build(check_output: RunOutput | None = None) -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    config = ServerConfig(godot_project_dir="/tmp/proj")
    bridge = Bridge(config.bridge, connector=connector_for(conn))
    runner = _FakeRunner(check_output or RunOutput(command=["fake"]))
    return create_server(config, bridge=bridge, runner=runner), conn


def test_parse_check_errors_extracts_line() -> None:
    text = (
        "SCRIPT ERROR: Parse Error: Expected expression after \"=\".\n"
        "          at: GDScript::reload (res://player.gd:3)\n"
        "ERROR: Failed to load script with error \"Parse error\"."
    )
    errors = parse_check_errors(text)
    assert len(errors) == 1
    assert errors[0].source == "res://player.gd"
    assert errors[0].line == 3
    assert "Expected expression" in errors[0].message


def test_parse_check_errors_ignores_non_parse_script_errors() -> None:
    # A non-parse SCRIPT ERROR (no "Parse Error:") must not be reported as a parse error.
    text = 'SCRIPT ERROR: Invalid call. Nonexistent function "foo".\n   at: (res://a.gd:9)'
    assert parse_check_errors(text) == []


async def test_script_tools_gated_in_scripts_toolset() -> None:
    server, _ = _build()
    async with Client(server) as client:
        assert "read_script" not in {t.name for t in await client.list_tools()}
        await client.call_tool("enable_toolset", {"category": "scripts"})
        names = {t.name for t in await client.list_tools()}
    assert {"read_script", "write_script", "patch_script", "get_parse_errors"} <= names


async def test_read_and_list_scripts() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        content = await client.call_tool("read_script", {"script_path": "res://a.gd"})
        listing = await client.call_tool("list_scripts", {"directory": "res://"})
    assert content.structured_content["content"] == "extends Node\n"
    assert listing.structured_content["scripts"] == ["res://a.gd", "res://b.gd"]


async def test_write_script_safety_and_dry_run() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        tool = next(t for t in await client.list_tools() if t.name == "write_script")
        assert tool.meta is not None and tool.meta.get("safety_class") == "mutating"
        dry = await client.call_tool(
            "write_script",
            {"script_path": "res://x.gd", "content": "extends Node", "dry_run": True},
        )
    assert dry.structured_content["dry_run"] is True
    sent = [CommandEnvelope.model_validate_json(s).command for s in conn.sent]
    assert "cmd_write_script" not in sent  # dry-run writes nothing


async def test_patch_script_routes() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "patch_script", {"script_path": "res://a.gd", "find": "foo", "replace": "bar"}
        )
    assert result.structured_content["replacements"] == 2


async def test_get_parse_errors_reports_structured_errors() -> None:
    check = RunOutput(
        command=["fake"],
        stderr="SCRIPT ERROR: Parse Error: bad\n   at: GDScript::reload (res://a.gd:5)",
    )
    server, _ = _build(check_output=check)
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        result = await client.call_tool("get_parse_errors", {"script_path": "res://a.gd"})
    payload = result.structured_content
    assert payload["ok"] is False
    assert payload["errors"][0]["line"] == 5


async def test_missing_script_is_structured_error() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "read_script", {"script_path": "res://missing.gd"}, raise_on_error=False
        )
    assert result.is_error
    assert "RESOURCE_NOT_FOUND" in str(result.content)
