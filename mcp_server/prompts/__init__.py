"""MCP prompts (``@mcp.prompt()``).

Step-numbered workflow templates that tell the agent which tools/resources to use
in what order. They instruct, they do not act. Prompts land in issue #12.
"""

from mcp_server.prompts.prompts import register_prompts

__all__ = ["register_prompts"]
