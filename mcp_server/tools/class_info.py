"""Core `godot_describe_class` tool: ClassDB metadata for agent discovery (#533).

Answers "what can I set on any Tween?" / "which args does Vector3 take?"
straight from ClassDB — no live node required, no instantiation. Read-only;
the only precondition is a connected bridge (route() surfaces it).
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.models.class_info import ClassInfo
from mcp_server.safety import READ_ONLY
from mcp_server.tools._route import route


def register_class_info(mcp: FastMCP, bridge: Bridge) -> None:
    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def describe_class(
        class_name: str, include_inherited: bool = False, include_private: bool = False
    ) -> ClassInfo:
        """Describe an engine class's ClassDB metadata: settable properties
        (with defaults and types), methods (typed args + return), signals,
        integer constants, enums, the inheritance chain, and instantiability.

        Use BEFORE setting properties or calling methods by trial-and-error:
        the ``type`` fields are Variant.Type names — exactly the shapes the
        coercion layer accepts for ``set_node_property`` values. Engine classes
        only (script ``class_name`` globals are not in ClassDB; an unknown name
        returns VALIDATION_ERROR with did-you-mean suggestions). Default flags
        list the class's OWN members; ``include_inherited=True`` widens every
        list to the full ancestry; ``include_private=True`` keeps
        ``_``-prefixed entries.
        """
        if not class_name.strip():
            raise ValueError("class_name must be a non-empty class name.")
        result = await route(
            bridge,
            "cmd_describe_class",
            {
                "class_name": class_name,
                "include_inherited": include_inherited,
                "include_private": include_private,
            },
        )
        return ClassInfo(**result)