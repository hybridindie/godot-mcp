"""godot-mcp FastMCP server package.

The AI-facing half of the system. Exposes MCP tools, resources, and prompts over
stdio and forwards every Godot operation to the editor addon over the WebSocket
bridge. This package owns all safety/precondition logic and the Pydantic domain
models; it holds no Godot logic itself.

See ``docs/architecture.md`` for the bridge contract.
"""

# CalVer, kept in sync with pyproject.toml and .opencode/rules/enforcement.md.
__version__ = "2026.08.31b4"

# Tool-contract / compatibility version — a monotonic integer, deliberately
# distinct from the CalVer build version. It expresses the *contract*: bump it
# only on a BREAKING change to the tool surface or bridge envelope (a removed/
# renamed tool, a changed required field, an envelope-shape change). Additive,
# backward-compatible changes (new tools, new optional fields) do NOT bump it.
# Clients negotiate against this via get_server_info — see docs/tool-contracts.md.
CONTRACT_VERSION = 1
# Oldest client contract version this server still serves. A client is compatible
# when MIN_COMPATIBLE_CONTRACT <= client_contract <= CONTRACT_VERSION.
MIN_COMPATIBLE_CONTRACT = 1
