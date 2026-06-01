"""Domain vocabulary tool (issue #7).

Exposes the tower-defense vocabulary (archetypes, placement types, wave
modifiers, run states) so an agent knows the valid terms before authoring towers,
enemies, and waves with the semantic tools in #8/#9. Read-only, no bridge call.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.models.domain import DomainVocabulary
from mcp_server.safety import READ_ONLY


def register_domain(mcp: FastMCP) -> None:
    """Register the domain-vocabulary introspection tool."""

    @mcp.tool(meta=READ_ONLY)
    async def get_domain_vocabulary() -> DomainVocabulary:
        """List the tower-defense vocabulary this server understands — tower and
        enemy archetypes, placement types, wave modifiers, and run states. Call
        this before creating towers/enemies/waves so you use valid values.
        """
        return DomainVocabulary.current()
