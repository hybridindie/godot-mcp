"""Contract test for the server-level MCP instructions.

The ``instructions`` string is returned in the MCP ``initialize`` handshake and
is the only guidance most clients surface to the model automatically (without a
user invoking a prompt). It must teach the must-know conventions so the model
behaves correctly with no human in the loop:

- toolset gating (enable a toolset before using its tools), and
- the safety convention (mutations accept ``dry_run``; destructive tools require
  ``confirm``).
"""

from __future__ import annotations

from typing import Any

import pytest

from mcp_server.server import create_server


@pytest.fixture
def instructions() -> str:
    """The server's top-level MCP instructions string."""
    server: Any = create_server()
    text: str = str(server.instructions)
    assert text, "server must set non-empty instructions"
    return text


def test_instructions_cover_toolset_gating(instructions: str) -> None:
    """The gating protocol is the first thing a model must know."""
    assert "enable_toolset" in instructions


def test_instructions_cover_safety_convention(instructions: str) -> None:
    """Mutations preview with dry_run; destructive ops require confirm."""
    assert "dry_run" in instructions
    assert "confirm" in instructions


def test_instructions_advertise_the_client_side_skills(instructions: str) -> None:
    """The skills are client-side and invisible to the server (#707); the model must
    at least know they exist, how to install them, and that absence is undetectable."""
    assert "godot-getting-started" in instructions
    assert "godot-playtest-and-debug" in instructions
    assert "godot-expert" in instructions
    assert "install-skills.sh" in instructions
    # Honest: the server can't know whether they're loaded — no false status claim.
    assert "cannot detect" in instructions
