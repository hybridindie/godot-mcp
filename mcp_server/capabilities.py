"""The ``godot_mcp`` experimental capability snapshot (issue #231/#313).

FastMCP 4.0 introduced the ``ServerExtension`` API (SEP-2133) for structured
opt-in server capabilities. A ``ServerExtension`` advertises its settings under
``ServerCapabilities.extensions[identifier]`` — a *distinct* field from
``ServerCapabilities.experimental``. The existing ``godot_mcp`` capability is
advertised under ``experimental`` (consumed by clients reading
``experimental.godot_mcp``), and the contract test
(``tests/contract/test_capabilities.py``) pins that location.

Migrating ``godot_mcp`` to ``ServerExtension.settings()`` would relocate it to
``capabilities.extensions["dev.godot/godot_mcp"]`` — a wire-level
capability-location change that breaks existing clients and the contract test.
That relocation is a backwards-incompatible contract change, out of scope for
this stabilization issue (which only replaces private-API reaches with the
public provider surface). When the contract is intentionally revised to move
``godot_mcp`` from ``experimental`` to the extensions slot, the natural
expression is a ``GodotMcpExtension(ServerExtension)`` whose ``settings()``
returns the snapshot below; the structure of this module is shaped so that
migration is a one-step move.

For now the snapshot is built from the public provider surface
(``manager.status()`` for toolset_count, and the registrant-reported prompt /
resource names) and written into ``experimental_capabilities["godot_mcp"]`` via
the FastMCP constructor / ``_apply_capabilities``. No ``_components`` reach is
required: the counts already come from the registry, not from introspecting
FastMCP internals.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.toolsets import ToolsetManager

CAPABILITY_KEY = "godot_mcp"

STATIC_CAPABILITY: dict[str, Any] = {
    "version": "2026.06.01",
    "min_godot": "4.4",
    "docs": {
        "tutorial": "https://github.com/hybridindie/godot-mcp/blob/main/TUTORIAL.md",
        "tool_contracts": "https://github.com/hybridindie/godot-mcp/blob/main/docs/tool-contracts.md",
        "architecture": "https://github.com/hybridindie/godot-mcp/blob/main/docs/architecture.md",
    },
}


def build_capability(
    manager: ToolsetManager, prompts: list[str], resources: list[str]
) -> dict[str, Any]:
    """Build the live ``godot_mcp`` capability snapshot from the registry.

    ``toolset_count`` comes from ``manager.status()`` (the gated toolsets plus
    the always-on ``core`` toolset — everything ``list_toolsets`` reports);
    ``prompts`` and ``resources`` are the names/URIs the registration functions
    report, so the snapshot tracks the catalog without introspecting FastMCP
    internals.
    """
    return {
        **STATIC_CAPABILITY,
        "toolset_count": len(manager.status()),
        "prompts": list(prompts),
        "resources": list(resources),
    }


def apply_capability(
    mcp: FastMCP, manager: ToolsetManager, prompts: list[str], resources: list[str]
) -> None:
    """Write the live snapshot into ``experimental_capabilities["godot_mcp"]``.

    The static fields (version / min_godot / docs) are seeded by the
    ``FastMCP`` constructor; this overwrites the dynamic fields
    (toolset_count / prompts / resources) from the live registry so they can
    never drift from the real catalog.
    """
    caps = mcp.experimental_capabilities[CAPABILITY_KEY]
    snapshot = build_capability(manager, prompts, resources)
    caps["toolset_count"] = snapshot["toolset_count"]
    caps["prompts"] = snapshot["prompts"]
    caps["resources"] = snapshot["resources"]
