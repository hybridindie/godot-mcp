"""Input-map mutations are undoable (issue #907).

The four input-map writers used to call ``ProjectSettings.set_setting`` + ``save``
with no UndoRedo, so Edit → Undo could not revert an agent's input-map edit and
the results reported ``reversible_by: "none"``. The headless smoke
(``godot/tests/input_map_undo_smoke.gd``) drives each writer through the real
router inside an editor process and undoes it; the server tests pin the
``reversible_by: "undo"`` claim every result now makes.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from tests.contract.test_input_map import _responder
from tests.fakes import FakeAddonConnection, connector_for
from tests.integration._godot import GODOT_BIN, run_godot

SMOKE = "input_map_undo_smoke.gd"


@pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed")
def test_input_map_undo_smoke_reverts_every_writer() -> None:
    """Undo on the editor history reverts add/remove action, add event and clear."""
    result = run_godot(["--editor", "--script", f"res://tests/{SMOKE}"])
    output = result.stdout + result.stderr
    assert "INPUT_MAP_UNDO_TEST_OK" in output, (
        f"input-map undo smoke did not pass (exit {result.returncode}):\n{output}"
    )
    assert "SCRIPT ERROR" not in output


_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("godot_input_map_add_action", {"name": "jump"}),
    ("godot_input_map_remove_action", {"name": "jump", "confirm": True}),
    ("godot_input_map_add_event", {"action": "jump", "event_type": "key", "keycode": "Space"}),
    ("godot_input_map_clear_action_events", {"action": "jump", "confirm": True}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool", "args"), _CALLS, ids=[c[0] for c in _CALLS])
async def test_input_map_results_report_undo(tool: str, args: dict[str, Any]) -> None:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "input_map"})
        result = await client.call_tool(tool, args)
    assert result.structured_content["reversible_by"] == "undo"
