"""Unit tests: the toolset protocol text is single-sourced (issue #230).

The toolset-gating protocol was duplicated across the server ``instructions`` and
the ``toolset_discovery`` prompt. Both must now compose from the same constants in
``mcp_server.toolset_protocol`` so the text cannot drift between them.
"""

from __future__ import annotations

import pytest

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
    assert "godot_list_toolsets" in TOOLSET_PROTOCOL
    assert "godot_enable_toolset" in TOOLSET_PROTOCOL


def test_gating_intro_states_effective_default_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gating text must reflect the *effective* default (issue #425): when
    GODOT_MCP_DEFAULT_TOOLSETS seeds more/all toolsets, static 'only core +
    inspection' text would tell the agent to enable toolsets it already has."""
    import importlib

    import mcp_server.toolset_protocol as protocol
    import mcp_server.toolsets as toolsets

    monkeypatch.setenv("GODOT_MCP_DEFAULT_TOOLSETS", "all")
    # protocol imports DEFAULT_ENABLED by name from toolsets — reload the source
    # module first, then the consumer, so the env change is observed.
    importlib.reload(toolsets)
    importlib.reload(protocol)
    intro = protocol.GATING_INTRO
    # With `all` seeded, the text must not claim everything is hidden...
    assert "Every other capability is hidden" not in intro
    # ...and must name the env override so the agent understands why.
    assert "GODOT_MCP_DEFAULT_TOOLSETS" in intro

    monkeypatch.delenv("GODOT_MCP_DEFAULT_TOOLSETS", raising=False)
    importlib.reload(toolsets)
    importlib.reload(protocol)
    # Unset keeps the documented default (core + inspection).
    assert "Only 'core'" in protocol.GATING_INTRO
    assert "inspection" in protocol.GATING_INTRO
    # Restore the ambient default for other tests (import-time state).
    from mcp_server.toolsets import DEFAULT_ENABLED

    assert DEFAULT_ENABLED == frozenset({"inspection"})
