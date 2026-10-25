"""E2E: project-tool discovery + schema generation, headless (#761).

Runs the addon's scanner through Godot itself, so the GDScript parser and the
static-type → JSON Schema mapping are exercised for real. Gated on a Godot
binary being installed (the one conditional skip the testing rules allow).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.integration._godot import GODOT_BIN, GODOT_PROJECT, run_godot

pytestmark = pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")

FIXTURE = GODOT_PROJECT / "e2e_project_tools.gd"
RUNNER = "res://addons/godot_mcp/project_tools_runner.gd"
MARKER = "GODOT_MCP_PROJECT_TOOLS "

SOURCE = """@tool
extends RefCounted

enum Kind { ENEMY, BOSS }

## Spawn a wave of enemies.
## @mcp_tool safety=mutating
func spawn_wave(count: int, kind: Kind = Kind.ENEMY, tags: Array[String] = []) -> Dictionary:
	return {"count": count}

## The wave spawn point.
## @mcp_tool safety=read_only
func spawn_point(where: Vector2) -> Vector2:
	return where

## Broken: the parameter has no static type.
## @mcp_tool
func loose(x) -> int:
	return 0

## Broken: a type the schema cannot describe.
## @mcp_tool
func resource_arg(res: Resource) -> int:
	return 0

## Broken: a required parameter after a default one.
## @mcp_tool
func bad_default(a: int = 1, b: int) -> int:
	return b

## Broken: the safety class is not one of the three.
## @mcp_tool safety=chaos
func wrong_safety() -> int:
	return 0
"""


def _scan() -> Any:
    result = run_godot(["--script", RUNNER])
    assert result.returncode == 0, result.stderr
    for line in result.stdout.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER) :])
    raise AssertionError(f"scanner did not print a result line:\n{result.stdout}")


def test_scanner_generates_schemas_and_rejects_untyped_parameters() -> None:
    FIXTURE.write_text(SOURCE, encoding="utf-8")
    try:
        payload = _scan()
    finally:
        FIXTURE.unlink(missing_ok=True)
        FIXTURE.with_suffix(".gd.uid").unlink(missing_ok=True)

    tools = {tool["function"]: tool for tool in payload["tools"]}
    assert set(tools) == {"spawn_wave", "spawn_point"}

    wave = tools["spawn_wave"]
    assert wave["safety_class"] == "mutating"
    assert wave["description"] == "Spawn a wave of enemies."
    props = wave["parameters"]["properties"]
    assert props["count"] == {"type": "integer"}
    assert props["kind"]["enum"] == ["ENEMY", "BOSS"]
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert wave["parameters"]["required"] == ["count"]

    point = tools["spawn_point"]
    assert point["safety_class"] == "read_only"
    assert point["parameters"]["properties"]["where"]["required"] == ["x", "y"]

    # Every rejected annotation names the function and the precise reason — one
    # bad function never hides the valid ones.
    rejected = {entry["function"]: entry["reason"] for entry in payload["rejected"]}
    assert set(rejected) == {"loose", "resource_arg", "bad_default", "wrong_safety"}
    assert "untyped parameter 'x'" in rejected["loose"]
    assert "unsupported type 'Resource'" in rejected["resource_arg"]
    assert "non-default parameter 'b'" in rejected["bad_default"]
    assert "unknown safety class 'chaos'" in rejected["wrong_safety"]
