"""Contract test: polymorphic ``value: Any`` setters document accepted shapes (issue #229).

Godot's value types are polymorphic (Vector2/Color/NodePath/…); the agent gets no
schema hint from ``value: Any``. Each setter's docstring must spell out the accepted
JSON shapes with concrete examples so first-try calls aren't malformed.
"""

from __future__ import annotations

import asyncio

from mcp_server.server import create_server

# Every tool that takes a polymorphic ``value: Any``.
VALUE_SETTERS = {
    "set_setting",
    "set_shader_param",
    "set_shader_node_param",
    "set_node_property",
    "batch_set_property",
    "cross_scene_set_property",
    "insert_keyframe",
    "set_resource_property",
}

# Concrete shape markers the docstring must mention to actually guide the agent.
REQUIRED_MARKERS = ("Vector2", "Color", "NodePath")


def test_value_setters_document_accepted_shapes() -> None:
    server = create_server()
    tools = {t.name: t for t in asyncio.run(server._list_tools())}

    missing_tools = VALUE_SETTERS - set(tools)
    assert not missing_tools, f"setter tools not found: {sorted(missing_tools)}"

    offenders: list[str] = []
    for name in VALUE_SETTERS:
        doc = tools[name].description or ""
        if not all(marker in doc for marker in REQUIRED_MARKERS):
            offenders.append(name)
    assert not offenders, f"setters missing value-shape docs: {sorted(offenders)}"
