"""Unit tests: the toolset protocol text is single-sourced (issue #230).

The toolset-gating protocol was duplicated across the server ``instructions`` and
the ``toolset_discovery`` prompt. Both must now compose from the same constants in
``mcp_server.toolset_protocol`` so the text cannot drift between them.
"""

from __future__ import annotations

from mcp_server.server import create_server
from mcp_server.toolset_protocol import (
    COMMON_TOOLSETS,
    GATING_INTRO,
    TOOLSET_PROTOCOL,
)


def test_server_instructions_use_shared_protocol() -> None:
    server = create_server()
    assert server.instructions is not None
    # The shared protocol block is the source of the instructions' gating text.
    assert GATING_INTRO in server.instructions
    assert COMMON_TOOLSETS in server.instructions


def test_toolset_discovery_prompt_uses_shared_protocol() -> None:
    import asyncio

    server = create_server()
    result = asyncio.run(server.render_prompt("toolset_discovery"))
    # Read the raw text (not the TextContent repr, which escapes newlines).
    content = "\n".join(getattr(m.content, "text", str(m.content)) for m in result.messages)
    # Same shared fragments appear verbatim in the prompt — single source.
    assert GATING_INTRO in content
    assert COMMON_TOOLSETS in content


def test_shared_protocol_is_self_consistent() -> None:
    # The composed protocol contains each of its parts (guards accidental drift in
    # the join).
    assert GATING_INTRO in TOOLSET_PROTOCOL
    assert COMMON_TOOLSETS in TOOLSET_PROTOCOL
    # And it still names the two calls the agent must make.
    assert "list_toolsets" in TOOLSET_PROTOCOL
    assert "enable_toolset" in TOOLSET_PROTOCOL
