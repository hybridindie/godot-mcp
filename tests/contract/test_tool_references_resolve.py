"""Contract: every ``godot_*`` tool reference in server hints/docstrings resolves
to a real tool (issue #652).

Agent-facing hints and docstrings that name a nonexistent tool cost a failed
round-trip each. This scans every string literal / docstring in ``mcp_server``
for ``godot_<toolset>_…`` tokens (plus truncated ``godot_<toolset>``) and asserts
each is a registered tool name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.server import create_server
from mcp_server.toolsets import TOOLSETS
from mcp_server.transforms import _original_handler_name, godot_tool_name
from tests.fakes import FakeAddonConnection, connector_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "mcp_server"
_TOKEN = re.compile(r"\bgodot_[a-z0-9_]+")  # pragma: allowlist secret (tool-name regex)
# `godot_project_dir` is a config field, not a tool (its "project_" prefix makes
# it look like the `project` toolset).
_NON_TOOL = {"godot_project_dir"}


def _is_tool_reference(token: str) -> bool:
    rest = token[len("godot_") :]
    toolsets = set(TOOLSETS) | {"core"}
    return any(rest == ts or rest.startswith(ts + "_") for ts in toolsets)


async def _registered_tool_names() -> set[str]:
    conn = FakeAddonConnection()
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    mcp = create_server(ServerConfig(), bridge=bridge)
    return {
        godot_tool_name(_original_handler_name(t), t.tags)
        for t in await mcp.local_provider.list_tools()
    }


@pytest.mark.asyncio
async def test_every_tool_reference_resolves() -> None:
    registered = await _registered_tool_names()
    problems: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        for match in _TOKEN.finditer(path.read_text(encoding="utf-8")):
            token = match.group(0)
            if token in _NON_TOOL or not _is_tool_reference(token):
                continue
            if token not in registered:
                problems.append(f"{path.relative_to(_REPO_ROOT)}: {token}")
    assert not problems, (
        "server hints/docstrings name tools that don't exist (#652):\n" + "\n".join(problems)
    )
