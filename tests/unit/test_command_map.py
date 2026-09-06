"""Unit tests for the run_commands bare-name table (mcp_server/command_map.py).

The table is static by design (no registry dependency at request time), so a
drift test pins it against the live registry: every bridge-routed tool must be
resolvable, and every table entry must map to a command some tool actually
routes. This is the guard that keeps #420/#421 fixed as the surface grows.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from mcp_server.command_map import (
    BARE_TO_COMMAND,
    ORCHESTRATORS,
    map_params,
    resolve_command,
)

# ---------------------------------------------------------------- unit basics


def test_resolve_accepts_cmd_form_verbatim() -> None:
    assert resolve_command("cmd_set_node_property") == "cmd_set_node_property"


def test_resolve_trimmed_and_reordered_names() -> None:
    assert resolve_command("physics_set_layers") == "cmd_set_physics_layers"
    assert resolve_command("particles_apply_preset") == "cmd_apply_particle_preset"
    assert resolve_command("write_script") == "cmd_write_script"
    assert resolve_command("add_bus") == "cmd_add_audio_bus"
    assert resolve_command("get_bus_layout") == "cmd_get_audio_bus_layout"
    assert resolve_command("read_shader") == "cmd_read_shader"
    assert resolve_command("get_shader_param") == "cmd_get_shader_param"


def test_resolve_plain_handler_name() -> None:
    assert resolve_command("create_node") == "cmd_create_node"
    assert resolve_command("set_node_property") == "cmd_set_node_property"


def test_resolve_unknown_suggests_closest() -> None:
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        resolve_command("set_layerz")
    assert "set_layers" in str(exc.value)


def test_resolve_ambiguous_names_both_toolsets() -> None:
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc:
        resolve_command("set_layers")
    assert "navigation_set_layers" in str(exc.value)
    assert "physics_set_layers" in str(exc.value)


def test_resolve_orchestrator_gets_targeted_hint() -> None:
    from fastmcp.exceptions import ToolError

    for name in ("run_tests", "run_test_scenario", "export_project"):
        with pytest.raises(ToolError) as exc:
            resolve_command(name)
        assert "directly" in str(exc.value)


def test_table_has_no_orchestrator_overlap() -> None:
    assert not (set(BARE_TO_COMMAND) & set(ORCHESTRATORS))


def test_map_params_translates_node_name() -> None:
    mapped = map_params(
        "create_node", {"parent_path": ".", "node_type": "Area3D", "node_name": "X"}
    )
    assert mapped == {"parent_path": ".", "node_type": "Area3D", "name": "X"}
    # explicit "name" wins; node_name is dropped
    mapped = map_params("create_node", {"name": "Y", "node_name": "X"})
    assert mapped == {"name": "Y"}
    # unknown names pass through untouched
    assert map_params("nope", {"node_name": "Z"}) == {"node_name": "Z"}


# ---------------------------------------------------------------- drift guard


def _scrape_fn_cmds() -> dict[str, list[str]]:
    """fn name -> every cmd_ literal it routes (module + delegate helpers)."""
    fn_cmds: dict[str, list[str]] = {}
    tool_re = re.compile(r"async def ([a-z_]+)\(")
    route_re = re.compile(r'"(cmd_[a-z_]+)"')
    for path in Path("mcp_server/tools").glob("*.py"):
        current: str | None = None
        for line in path.read_text().splitlines():
            m = tool_re.search(line)
            if m:
                current = m.group(1)
            for r in route_re.finditer(line):
                if current:
                    fn_cmds.setdefault(current, [])
                    if r.group(1) not in fn_cmds[current]:
                        fn_cmds[current].append(r.group(1))
    return fn_cmds


def _live_registry() -> list[tuple[str, str]]:
    """(exposed name, handler fn name) for every registered tool."""
    os.environ.setdefault("GODOT_MCP_DEFAULT_TOOLSETS", "all")
    from mcp_server.bridge import Bridge
    from mcp_server.config import ServerConfig
    from mcp_server.server import create_server
    from mcp_server.transforms import _original_handler_name, godot_tool_name
    from tests.fakes import FakeAddonConnection, connector_for

    async def collect() -> list[tuple[str, str]]:
        conn = FakeAddonConnection()
        bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
        server = create_server(ServerConfig(), bridge=bridge)
        tools = await server.local_provider.list_tools()
        return [
            (godot_tool_name(_original_handler_name(t), t.tags), _original_handler_name(t))
            for t in tools
        ]

    return asyncio.run(collect())


def test_every_bridge_tool_bare_name_resolves_or_is_exempted() -> None:
    """Drift guard: every registered tool's bare name either resolves to the
    command its fn routes, or is in a documented exemption bucket."""
    fn_cmds = _scrape_fn_cmds()
    # multi-step orchestrators and no-bridge-command tools must NOT be in the table
    exempt_no_cmd = {
        # pure-python: analysis service, toolset mgmt, health, server info
        "analyze_dependencies", "analyze_signal_flow", "cross_scene_find_refs",
        "detect_circular_dependencies", "find_orphaned_resources",
        "find_unused_resources", "project_stats", "project_structure",
        "validate_scene_integrity", "enable_toolset", "disable_toolset",
        "get_server_info", "health_check", "list_toolsets",
        "list_tools_by_safety_class", "read_resource",
        # shells out to the Godot binary
        "get_parse_errors",
        # multi-step orchestrators (run several commands / binary runs)
        "debug_workflow", "run_tests", "run_test_scenario", "run_stress_test",
        "run_and_capture", "export_project", "assert_node_state",
        "compare_screenshots",
    }
    # delegated fns: the literal lives in a module-level helper, not the tool fn
    delegated: dict[str, str] = {
        "set_node_property": "cmd_set_node_property",  # _try_set_with_suggestions
    }
    problems: list[str] = []
    for exposed, fn in _live_registry():
        bare = exposed.removeprefix("godot_")
        if bare in BARE_TO_COMMAND:
            cmds = fn_cmds.get(fn) or ([delegated[fn]] if fn in delegated else [])
            if cmds and BARE_TO_COMMAND[bare] not in cmds:
                problems.append(f"{bare}: table says {BARE_TO_COMMAND[bare]}, fn routes {cmds}")
            continue
        if bare in ORCHESTRATORS or fn in exempt_no_cmd or fn in delegated:
            continue
        if fn.startswith("_"):
            continue
        if not fn_cmds.get(fn):
            continue  # genuinely no bridge command
        problems.append(f"{bare} (fn {fn}) routes {fn_cmds[fn]} but has no table entry")
    assert not problems, "command_map drift:\n" + "\n".join(problems)


def test_every_table_target_is_a_real_routed_command() -> None:
    """Reverse guard: each table value must be a cmd_ literal routed by some fn
    (no typos into nonexistent handlers)."""
    fn_cmds = _scrape_fn_cmds()
    routed = {c for cmds in fn_cmds.values() for c in cmds}
    missing = {bare: cmd for bare, cmd in BARE_TO_COMMAND.items() if cmd not in routed}
    assert not missing, f"table entries routing nowhere: {missing}"