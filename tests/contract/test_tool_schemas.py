"""Contract: tool schemas are tight — enums, and a docstring budget (issue #654).

Every tool's description is loaded into the agent's context for every enabled
toolset, so a bloated docstring is a recurring cost; closed vocabularies should
be published as enums so clients guide generation instead of failing late.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.transforms import _original_handler_name, godot_tool_name
from tests.fakes import FakeAddonConnection, connector_for

# Every tool description must fit this budget (chars); long guidance belongs in
# skills/docs, not the per-tool docstring.
_DESCRIPTION_BUDGET = 1100
# And the whole surface (sum of descriptions) must fit this.
_TOTAL_BUDGET = 62_000


async def _tools() -> list[Any]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    mcp = create_server(ServerConfig(), bridge=bridge)
    return list(await mcp.local_provider.list_tools())


@pytest.mark.asyncio
async def test_every_tool_description_fits_the_budget() -> None:
    over = [
        (godot_tool_name(_original_handler_name(t), t.tags), len(t.description or ""))
        for t in await _tools()
        if len(t.description or "") > _DESCRIPTION_BUDGET
    ]
    assert not over, (
        f"tool descriptions over the {_DESCRIPTION_BUDGET}-char budget (#654): {over}. "
        "Move guidance into docs/skills."
    )


@pytest.mark.asyncio
async def test_total_description_budget() -> None:
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= _TOTAL_BUDGET, f"total tool docstring size {total} > {_TOTAL_BUDGET} (#654)"


@pytest.mark.asyncio
async def test_closed_vocab_uses_an_enum() -> None:
    """`godot_scripts_list`'s `language` is a closed set → published as an enum in
    the JSON schema so clients can't send an invalid value."""
    tools = {godot_tool_name(_original_handler_name(t), t.tags): t for t in await _tools()}
    params = tools["godot_scripts_list"].parameters or {}
    language = params["properties"]["language"]
    assert language.get("enum") == ["gd", "cs"], language


@pytest.mark.asyncio
async def test_structured_dict_params_get_a_schema() -> None:
    """#691: the known-shape dict params resolve to typed models, so their fields
    appear in the published schema (not a bare ``object``)."""
    tools = {godot_tool_name(_original_handler_name(t), t.tags): t for t in await _tools()}
    expected = {
        "godot_composite_run_commands": ("commands", "RunCommandEntry"),
        "godot_composite_compose_node": ("children", "ChildSpec"),
        "godot_composite_apply_node_edits": ("edits", "NodeEdit"),
        "godot_asset_import_asset": ("options", "ImportOptions"),
    }
    for name, (_prop, model) in expected.items():
        schema = tools[name].parameters or {}
        assert model in schema.get("$defs", {}), f"{name} is missing the {model} schema (#691)"
