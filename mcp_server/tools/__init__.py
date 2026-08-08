"""MCP tool handlers (``@mcp.tool()``).

Delegation only: validate typed args, check preconditions, call the bridge or a
service, return a typed Pydantic model. Zero domain logic here
(see .opencode/rules/architecture.md). Tools land starting in issue #5.
"""
