"""E2E: validate_project discovers a project validator and runs it headless (#758)."""

from __future__ import annotations

import asyncio
import shutil

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.runtime import find_godot_binary
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for
from tests.integration._godot import GODOT_BIN, GODOT_PROJECT

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

VALIDATOR = GODOT_PROJECT / ".mcp" / "validators" / "e2e_validator.gd"
VALIDATOR_DIR = GODOT_PROJECT / ".mcp"


def _validator_source() -> str:
    return """@tool
extends RefCounted


func validate(_context: Dictionary) -> Array:
	return [{
		"severity": "error",
		"path": "res://e2e_missing.tscn",
		"message": "E2E validator finding",
	}]
"""


async def _run() -> None:
    VALIDATOR.parent.mkdir(parents=True, exist_ok=True)
    VALIDATOR.write_text(_validator_source(), encoding="utf-8")
    try:
        config = ServerConfig(
            godot_bin=GODOT_BIN,
            godot_project_dir=str(GODOT_PROJECT),
        )
        bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
        server = create_server(config, bridge=bridge)
        async with Client(server) as client:
            await client.call_tool("godot_enable_toolset", {"category": "analysis"})
            result = await client.call_tool("godot_analysis_validate_project", {})
        assert result.structured_content["valid"] is False
        findings = result.structured_content["findings"]
        custom = [
            f for f in findings if f.get("message") == "E2E validator finding"
        ]
        assert custom, f"custom validator finding missing: {findings}"
        assert custom[0]["validator"].endswith("e2e_validator.gd")
        assert custom[0]["severity"] == "error"
        assert any(v.endswith("e2e_validator.gd") for v in result.structured_content["validators"])
    finally:
        shutil.rmtree(VALIDATOR_DIR, ignore_errors=True)


def test_validate_project_runs_a_registered_validator() -> None:
    assert find_godot_binary(ServerConfig(godot_bin=GODOT_BIN)) is not None
    asyncio.run(_run())


TWO_FINDINGS_VALIDATOR = """@tool
extends RefCounted


func validate(_context: Dictionary) -> Array:
	return [
		{"severity": "error", "path": "res://scripts/missing.tscn", "message": "in scripts"},
		{"severity": "error", "path": "res://other/missing.tscn", "message": "in other"},
	]
"""


async def _scoped() -> None:
    VALIDATOR.parent.mkdir(parents=True, exist_ok=True)
    VALIDATOR.write_text(TWO_FINDINGS_VALIDATOR, encoding="utf-8")
    try:
        config = ServerConfig(godot_bin=GODOT_BIN, godot_project_dir=str(GODOT_PROJECT))
        bridge = Bridge(config.bridge, connector=connector_for(FakeAddonConnection()))
        server = create_server(config, bridge=bridge)
        async with Client(server) as client:
            await client.call_tool("godot_enable_toolset", {"category": "analysis"})
            folder = await client.call_tool(
                "godot_analysis_validate_project", {"paths": ["res://scripts"]}
            )
            one_file = await client.call_tool(
                "godot_analysis_validate_project",
                {"paths": ["res://other/missing.tscn"]},
            )
            outside = await client.call_tool(
                "godot_analysis_validate_project", {"paths": ["res://unrelated"]}
            )
            bad = await client.call_tool(
                "godot_analysis_validate_project",
                {"paths": ["/etc"]},
                raise_on_error=False,
            )
        folder_messages = [f["message"] for f in folder.structured_content["findings"]]
        assert "in scripts" in folder_messages and "in other" not in folder_messages
        assert folder.structured_content["scoped_to"] == ["res://scripts"]
        file_messages = [f["message"] for f in one_file.structured_content["findings"]]
        assert "in other" in file_messages and "in scripts" not in file_messages
        assert one_file.structured_content["scoped_to"] == ["res://other/missing.tscn"]
        assert outside.structured_content["findings"] == []
        assert outside.structured_content["valid"] is True
        assert bad.is_error
    finally:
        shutil.rmtree(VALIDATOR_DIR, ignore_errors=True)


def test_validate_project_scopes_to_a_file_or_folder() -> None:
    asyncio.run(_scoped())
