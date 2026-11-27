"""Unit: the guard-pattern approval is bound to the call it approved (#346 follow-up).

The first round seals ``{tool, safety_class, params}`` into ``request_state``,
but the continuation round only reads ``input_responses["approve"]``. An
approval for one set of arguments therefore authorizes any other set.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp.exceptions import ToolError

from mcp_server.approval_middleware import APPROVE_KEY, ApprovalMiddleware
from mcp_server.safety import ApprovalGate

pytestmark = pytest.mark.asyncio


class _Server:
    async def get_tool(self, name: str) -> Any:
        return SimpleNamespace(name=name, meta={"safety_class": "mutating"}, parameters={})


def _context(*, arguments: dict[str, Any], request_state: str | None) -> Any:
    accepted = SimpleNamespace(action="accept", content={"approve": True})
    fctx = SimpleNamespace(
        fastmcp=_Server(),
        input_responses={APPROVE_KEY: accepted},
        request_state=request_state,
    )
    message = SimpleNamespace(name="godot_scene_edit_create_node", arguments=arguments)
    return SimpleNamespace(message=message, fastmcp_context=fctx)


async def test_approval_for_other_arguments_does_not_run_the_tool() -> None:
    approved_state = json.dumps(
        {
            "tool": "godot_scene_edit_create_node",
            "safety_class": "mutating",
            "params": {"parent_path": ".", "node_type": "Node2D", "node_name": "Harmless"},
        }
    )
    context = _context(
        arguments={"parent_path": ".", "node_type": "Node2D", "node_name": "Different"},
        request_state=approved_state,
    )
    ran: list[bool] = []

    async def call_next(_ctx: Any) -> str:
        ran.append(True)
        return "ran"

    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    with pytest.raises(ToolError):
        await middleware.on_call_tool(context, call_next)
    assert ran == []


async def test_continuation_without_request_state_does_not_run_the_tool() -> None:
    context = _context(
        arguments={"parent_path": ".", "node_type": "Node2D", "node_name": "X"},
        request_state=None,
    )
    ran: list[bool] = []

    async def call_next(_ctx: Any) -> str:
        ran.append(True)
        return "ran"

    middleware = ApprovalMiddleware(ApprovalGate(require_approval=True))
    with pytest.raises(ToolError):
        await middleware.on_call_tool(context, call_next)
    assert ran == []
