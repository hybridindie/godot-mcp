"""Godot Editor MCP FastMCP server package.

The AI-facing half of the system. Exposes MCP tools, resources, and prompts over
stdio and forwards every Godot operation to the editor addon over the WebSocket
bridge. This package owns all safety/precondition logic and the Pydantic domain
models; it holds no Godot logic itself.

See ``docs/architecture.md`` for the bridge contract.
"""

# CalVer, kept in sync with pyproject.toml and .opencode/rules/enforcement.md.
__version__ = "2026.10.24"

# Tool-contract / compatibility version — a monotonic integer, deliberately
# distinct from the CalVer build version. It expresses the *contract*: the
# stable public surface clients build against (tools, params, result fields,
# value shapes, envelope, errors, safety semantics, toolsets). Bump it only on
# a BREAKING change (removed/renamed tool, changed required field or result
# field, envelope-shape change, changed existing-error-code meaning, or changed
# safety class / dry_run / confirm requirement). Additive changes (new tools,
# toolsets, prompts, resources, optional fields, new error codes) do NOT bump it.
# Clients negotiate against this via get_server_info — see
# docs/tool-contracts.md and the site's "The compatibility contract" page.
CONTRACT_VERSION = 1
# Oldest client contract version this server still serves. A client is compatible
# when MIN_COMPATIBLE_CONTRACT <= client_contract <= CONTRACT_VERSION.
MIN_COMPATIBLE_CONTRACT = 1
