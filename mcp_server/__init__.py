"""godot-mcp FastMCP server package.

The AI-facing half of the system. Exposes MCP tools, resources, and prompts over
stdio and forwards every Godot operation to the editor addon over the WebSocket
bridge. This package owns all safety/precondition logic and the Pydantic domain
models; it holds no Godot logic itself.

See ``docs/architecture.md`` for the bridge contract.
"""

# CalVer, kept in sync with pyproject.toml and .claude/rules/enforcement.md.
__version__ = "2026.06.01"
