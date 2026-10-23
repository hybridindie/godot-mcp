"""Fallback change receipts for mutating results (issue #756).

The core families (node, batch/composite, file/resource/script/shader) build a
precise receipt in the addon from its read-back. The remaining handlers return
their normal result fields; this middleware fills a **coarse** receipt for any
mutating/destructive result that did not supply one, using the addon's result
flags plus the call's path/value arguments. A handler-specific receipt always
wins (the middleware is a no-op when ``structured_content["receipt"]`` exists).

This keeps the receipt guarantee total (every mutating tool carries one) while
the precise read-back implementations continue to land per domain.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp.server.middleware import Middleware
from mcp.types import TextContent

from mcp_server.models.receipt import ChangeOp, ReceiptStatus

# Result flags that prove an effect, in priority order.
_CREATED = (
    "created",
    "added",
    "registered",
    "connected",
    "opened",
    "instanced",
    "extracted",
    "imported",
)
_UPDATED = (
    "set",
    "changed",
    "renamed",
    "moved",
    "assigned",
    "baked",
    "cleared",
    "removed",
    "deleted",
    "saved",
    "undone",
    "redone",
    "reloaded",
)
_EXISTED = (
    "already_connected",
    "already_open",
    "would_overwrite",
)
_NOOP = ("nothing_to_undo", "nothing_to_redo")

_PATH_KEYS = (
    "node_path",
    "resource_path",
    "script_path",
    "shader_path",
    "tileset_path",
    "library_path",
    "target_path",
    "new_path",
    "scene_path",
    "path",
    "name",
    "bus",
    "action",
)
_ADD_OPS = {"created", "added", "registered", "connected", "opened", "instanced", "imported"}
_REMOVE_OPS = {"deleted", "removed", "cleared", "closed", "disconnected"}
_WRITE_OPS = {"resource", "script", "shader", "import", "texture", "material"}
_CREATE_NAME = ("add", "create", "register", "connect", "open", "instance", "import", "extract")
_REMOVE_NAME = ("remove", "delete", "clear", "close", "disconnect")
_RENAME_NAME = ("rename", "move")


def synthesize_receipt(
    tool_name: str, args: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """A coarse receipt from the addon result + the call's path/value args."""
    status = _status(tool_name, result)
    path = _path(args, result, tool_name)
    op = _op(tool_name, result)
    before = _first(result, ("before", "old_value", "old_name", "previous"))
    after = _first(result, ("after", "value", "new_value", "new_name"))
    changes: list[dict[str, Any]] = []
    if path and status not in (ReceiptStatus.NOOP, ReceiptStatus.EXISTED):
        changes.append(
            {
                "path": path,
                "op": op.value,
                "before": before,
                "after": after if after is not None else result.get("name"),
            }
        )
    return {"status": status.value, "changes": changes, "truncated": False}


def _status(tool_name: str, result: dict[str, Any]) -> ReceiptStatus:
    if any(bool(result.get(k)) for k in _NOOP):
        return ReceiptStatus.NOOP
    if any(bool(result.get(k)) for k in _EXISTED):
        return ReceiptStatus.EXISTED
    # An explicit false effect flag is an honest noop (silent drop).
    for key in ("set", "changed", "added", "created", "saved"):
        if key in result and result[key] is False:
            return ReceiptStatus.NOOP
    if any(bool(result.get(k)) for k in _UPDATED):
        return ReceiptStatus.UPDATED
    if any(bool(result.get(k)) for k in _CREATED):
        return ReceiptStatus.CREATED
    lowered = tool_name.lower()
    if any(token in lowered for token in _CREATE_NAME):
        return ReceiptStatus.CREATED
    return ReceiptStatus.UPDATED


def _path(args: dict[str, Any], result: dict[str, Any], tool_name: str) -> str:
    for source in (result, args):
        for key in _PATH_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
    return tool_name


def _op(tool_name: str, result: dict[str, Any]) -> ChangeOp:
    lowered = tool_name.lower()
    if (
        (result.get("old_path") and result.get("new_path"))
        or result.get("renamed")
        or result.get("moved")
        or any(token in lowered for token in _RENAME_NAME)
    ):
        return ChangeOp.RENAME
    if any(bool(result.get(k)) for k in _REMOVE_OPS):
        return ChangeOp.REMOVE
    if any(token in lowered for token in ("resource", "script", "import", "texture", "material")):
        return ChangeOp.WRITE
    if lowered.startswith(("create_shader", "write_", "patch_")):
        return ChangeOp.WRITE
    if any(bool(result.get(k)) for k in _ADD_OPS):
        return ChangeOp.ADD
    if any(token in lowered for token in _CREATE_NAME):
        return ChangeOp.ADD
    if any(token in lowered for token in _REMOVE_NAME):
        return ChangeOp.REMOVE
    return ChangeOp.SET


def _first(result: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in result:
            return result[key]
    return None


async def apply_receipt_schema(mcp: Any) -> None:
    """Advertise the fallback ``receipt`` field on every mutating tool's schema.

    The middleware may add the field at call time; a client validating
    structuredContent against the declared outputSchema must see it declared.
    """
    for tool in await mcp.local_provider.list_tools():
        if (getattr(tool, "meta", None) or {}).get("safety_class") not in (
            "mutating",
            "destructive",
        ):
            continue
        schema = getattr(tool, "output_schema", None)
        if not isinstance(schema, dict):
            continue
        props = schema.setdefault("properties", {})
        props.setdefault("receipt", {"type": "object", "additionalProperties": True})


class ReceiptMiddleware(Middleware):
    """Ensure every successful mutating/destructive result has a receipt."""

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        result = await call_next(context)
        data = getattr(result, "structured_content", None)
        if not isinstance(data, dict) or getattr(result, "is_error", False):
            return result
        if data.get("receipt") is not None:
            return result
        safety_class = await _safety_class(context)
        if safety_class not in ("mutating", "destructive"):
            return result
        name = getattr(getattr(context, "message", None), "name", "<unknown>")
        args = dict(getattr(context.message, "arguments", None) or {})
        before = dict(data)
        data["receipt"] = synthesize_receipt(name, args, data)
        # Keep the text fallback in step with structuredContent (the MCP spec's
        # both-directions contract). Only rewrite text that was the JSON of the
        # result — a custom human summary is left alone.
        updated = []
        for block in getattr(result, "content", None) or []:
            if isinstance(block, TextContent):
                try:
                    if json.loads(block.text) == before:
                        block = block.model_copy(
                            update={"text": json.dumps(data, ensure_ascii=False)}
                        )
                except (TypeError, ValueError):
                    pass
            updated.append(block)
        result.content = updated
        return result


async def _safety_class(context: Any) -> str | None:
    try:
        tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
    except Exception:
        return None
    return (getattr(tool, "meta", None) or {}).get("safety_class")
