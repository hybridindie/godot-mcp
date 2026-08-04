"""The ``godot_mcp`` experimental capability snapshot (issue #231/#313/#332).

FastMCP 4.0b1 introduced the ``ServerExtension`` API (SEP-2133) for structured
opt-in server capabilities. A ``ServerExtension`` advertises its settings under
``ServerCapabilities.extensions[identifier]`` — a *distinct* wire field from
``ServerCapabilities.experimental``. The existing ``godot_mcp`` capability is
advertised under ``experimental`` (consumed by clients reading
``experimental.godot_mcp``), and the contract test
(``tests/contract/test_capabilities.py``) pins that location.

Issue #332 investigated migrating this snapshot onto a
``GodotMcpExtension(ServerExtension)``. Findings against FastMCP 4.0.0b1
(``fastmcp.server.extensions.ServerExtension``, located at
``fastmcp/server/extensions.py``):

* The full ``ServerExtension`` public surface is ``identifier``, ``settings()``,
  ``methods()``, ``lifespan()``, ``intercept_tool_call()``, ``client_settings()``
  plus the ``server`` property and ``_bind()``. There is **no hook to write into
  ``experimental_capabilities``** — extensions can only contribute to
  ``ServerCapabilities.extensions[identifier]``.
* ``settings()`` is hard-wired to ``capabilities.extensions[identifier]`` in
  ``FastMCPServerMiddleware.get_capabilities``
  (``fastmcp/server/low_level.py`` around the
  ``registered_extensions = {extension.identifier: extension.settings() ...}``
  block): the returned ``ServerCapabilities`` is rebuilt with
  ``extensions={**existing, UI_EXTENSION_ID: {}, **registered}``, and
  ``experimental`` is passed through unchanged from the constructor. So an
  extension cannot relocate its advertisement into ``experimental``.
* ``ServerExtension.identifier`` must match SEP-2133's reverse-DNS
  ``vendor-prefix/name`` grammar (``validate_extension_identifier`` rejects
  anything else). The bare ``godot_mcp`` key this module advertises today is
  *not* a valid extension identifier — the closest legal identifier is
  e.g. ``dev.godot/godot_mcp``. Any ``ServerExtension`` migration therefore
  forces a key rename in addition to the wire-field relocation, so it is
  doubly backwards-incompatible: clients reading
  ``experimental.godot_mcp`` would see nothing, and the new
  ``extensions["dev.godot/godot_mcp"]`` slot is a name they have never seen.

Conclusion: option (a) — keep the capability in ``experimental`` while using the
extension API — is **not expressible** in 4.0b1. The only available migration
(option b) relocates the snapshot to ``extensions[<reverse-dns>]`` with a
renamed key, breaking the contract test and any client consuming
``experimental.godot_mcp``. That is a wire-breaking contract change that needs
explicit sign-off, not a silent swap during stabilization. This issue is
therefore resolved as "documented why it can't be done without a
wire-breaking change"; the dict-mutation in ``apply_capability`` stays as the
intentional shape until the contract is revised.

When the contract is intentionally revised, the migration is a one-step move:
subclass ``ServerExtension`` with ``identifier = "dev.godot/godot_mcp"`` (or
whatever reverse-DNS prefix the contract lands on), override ``settings()`` to
return ``build_capability(...)`` below, register with ``mcp.add_extension(...)``,
and drop both the ``experimental_capabilities`` constructor seed and the
``apply_capability`` call. The snapshot construction (``build_capability``) is
already provider-surface-derived and unchanged by the relocation.

For now the snapshot is built from the public provider surface
(``manager.status()`` for toolset_count, and the registrant-reported prompt /
resource names) and written into ``experimental_capabilities["godot_mcp"]`` via
the FastMCP constructor / ``apply_capability``. No ``_components`` reach is
required: the counts already come from the registry, not from introspecting
FastMCP internals.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.toolsets import ToolsetManager

CAPABILITY_KEY = "godot_mcp"

# Note (issue #332): ``CAPABILITY_KEY`` is the *experimental-capabilities* key,
# not a valid ``ServerExtension.identifier`` — SEP-2133 requires a reverse-DNS
# ``vendor-prefix/name`` form (e.g. ``dev.godot/godot_mcp``). A future
# ServerExtension migration must rename the key, which is part of why it is a
# wire-breaking change. See the module docstring for the full 4.0b1 findings.

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
