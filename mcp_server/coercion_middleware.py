"""Argument coercion middleware — repairs stringified JSON parameters at the tools/call boundary.

Some MCP client harnesses serialize nested JSON objects/arrays (and even scalars)
as *strings* when constructing ``tools/call`` arguments. Pydantic then rejects
every ``properties``/``value``/``events``-style parameter with a ``dict_type``
validation error, silently making large parts of the tool surface unusable from
those clients. The server cannot change what the client sends, but it can
normalize it: this middleware walks the called tool's own input schema and
re-parses string arguments back into the shapes the schema declares.

Rules (conservative — a call that would have succeeded is never altered):
- ``type: "string"`` params are NEVER touched (script content, paths, enums stay intact).
- ``object``/``array`` params: a JSON string parsing to the declared kind is replaced.
- ``boolean``/``integer``/``number`` params: matching string forms are replaced.
- Untyped (``Any``) params — e.g. node ``value`` and assertion ``expected`` — may
  additionally repair JSON shapes, "true"/"false", and numeric strings.
- Recurses through nested object/array/$ref/allOf/anyOf/property schemas so
  stringified booleans inside a dict of properties are repaired too.

Fail-open: any error leaves the arguments untouched and the normal validation
path reports the original problem.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.server.middleware import Middleware

logger = logging.getLogger(__name__)

_BOOLS = {"true": True, "false": False}


def _resolve(schema: Any, root: dict[str, Any] | None) -> dict[str, Any] | None:
    """Follow ``$ref`` (local only) and flatten ``allOf`` into a plain schema dict."""
    while isinstance(schema, dict) and "$ref" in schema:
        ref = str(schema["$ref"])
        if root is None or not ref.startswith("#/"):
            return None
        node: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        schema = node
    if not isinstance(schema, dict):
        return None
    if "allOf" in schema:
        merged: dict[str, Any] = {k: v for k, v in schema.items() if k != "allOf"}
        for sub in schema.get("allOf") or []:
            resolved = _resolve(sub, root) or {}
            for key, val in resolved.items():
                if key == "properties" and isinstance(val, dict):
                    merged.setdefault("properties", {}).update(val)
                else:
                    merged[key] = val
        return merged
    return schema


def _branches(schema: dict[str, Any] | None, root: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Declared branch schemas for coercion (self + anyOf/oneOf alternatives)."""
    if schema is None:
        return []
    out = [schema]
    for key in ("anyOf", "oneOf"):
        for sub in schema.get(key) or []:
            resolved = _resolve(sub, root)
            if resolved is not None:
                out.append(resolved)
    return out


def _declared_types(branches: list[dict[str, Any]]) -> set[str]:
    types: set[str] = set()
    for branch in branches:
        t = branch.get("type")
        if isinstance(t, str):
            types.add(t)
        elif isinstance(t, list):
            types.update(x for x in t if isinstance(x, str))
    return types


def _parse_typed(s: str, types: set[str]) -> tuple[bool, Any]:
    """Parse ``s`` per the declared JSON-schema types. Returns (replaced, value)."""
    stripped = s.strip()
    if "boolean" in types:
        low = stripped.lower()
        if low in _BOOLS:
            return True, _BOOLS[low]
    if "object" in types and stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return False, s
        if isinstance(parsed, dict):
            return True, parsed
        return False, s
    if "array" in types and stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return False, s
        if isinstance(parsed, list):
            return True, parsed
        return False, s
    if "integer" in types:
        try:
            return True, int(stripped)
        except ValueError:
            pass
    if "number" in types:
        try:
            value = float(stripped)
        except ValueError:
            return False, s
        if value == value and value not in (float("inf"), float("-inf")):
            return True, value
        return False, s
    return False, s


def _parse_untyped(s: str) -> tuple[bool, Any]:
    """Best-effort repair for params with no declared type (``Any`` fields like
    ``value``/``expected``). Only repairs unambiguous JSON shapes, JSON
    booleans, and numeric strings — everything else stays a string."""
    stripped = s.strip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return False, s
        return (True, parsed) if isinstance(parsed, (dict, list)) else (False, s)
    low = stripped.lower()
    if low in _BOOLS:
        return True, _BOOLS[low]
    try:
        return True, int(stripped)
    except ValueError:
        pass
    try:
        value = float(stripped)
    except ValueError:
        return False, s
    return (True, value) if value == value and abs(value) != float("inf") else (False, s)


def _coerce_string(val: str, schema: dict[str, Any] | None, root: dict[str, Any] | None) -> Any:
    if schema and "enum" in schema:
        return val
    branches = _branches(schema, root)
    types = _declared_types(branches)
    if "string" in types:
        return val
    if not schema and types:
        return val
    if types:
        # A declared string branch returned above (a literal string is a valid
        # value there and is never altered), so only object/array/bool/number
        # declarations reach here: match the parsed shape against them.
        replaced, parsed = _parse_typed(val, types)
        if replaced:
            return _coerce_value(parsed, schema, root)
        return val
    replaced, parsed = _parse_untyped(val)
    if replaced:
        return _coerce_value(parsed, schema, root)
    return val


def _coerce_value(val: Any, schema: dict[str, Any] | None, root: dict[str, Any] | None) -> Any:
    if isinstance(val, str):
        return _coerce_string(val, schema, root)
    if isinstance(val, dict):
        resolved = _resolve(schema, root) or {}
        props = resolved.get("properties")
        addl = resolved.get("additionalProperties")
        out: dict[str, Any] = {}
        for key, sub_val in val.items():
            sub_schema: Any = None
            if isinstance(props, dict) and key in props:
                sub_schema = props[key]
            elif isinstance(addl, dict):
                sub_schema = addl
            out[key] = _coerce_value(sub_val, _resolve(sub_schema, root), root)
        return out
    if isinstance(val, list):
        resolved = _resolve(schema, root) or {}
        items = _resolve(resolved.get("items"), root)
        return [_coerce_value(item, items, root) for item in val]
    return val


def coerce_arguments(schema: dict[str, Any] | None, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return ``arguments`` normalized against a tool's input JSON schema.

    Only replaces values; never adds or removes keys. With ``schema=None`` the
    arguments are returned untouched (fail-open when the tool is unknown).
    """
    if schema is None or not isinstance(arguments, dict) or not arguments:
        return arguments
    props = schema.get("properties") if isinstance(schema, dict) else None
    out: dict[str, Any] = {}
    for key, val in arguments.items():
        sub = props.get(key) if isinstance(props, dict) else None
        out[key] = _coerce_value(val, _resolve(sub, schema), schema)
    return out


class ArgumentCoercionMiddleware(Middleware):
    """Apply :func:`coerce_arguments` to every ``tools/call`` before validation.

    Registered directly inside ``AgentErrorMiddleware`` (which stays outermost to
    catch every error) so every argument-reading gate (readiness, consent,
    approval, toolset gating) sees properly typed ``dry_run``/``confirm``/
    ``category`` values (#872).
    """

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        message = context.message
        arguments = getattr(message, "arguments", None)
        if isinstance(arguments, dict) and arguments:
            try:
                fastmcp = getattr(getattr(context, "fastmcp_context", None), "fastmcp", None)
                tool = await fastmcp.get_tool(message.name) if fastmcp is not None else None
                if tool is not None:
                    coerced = coerce_arguments(tool.parameters, arguments)
                    if coerced != arguments:
                        message.arguments = coerced
            except Exception:
                # Fail-open: leave the original arguments for normal validation.
                logger.debug(
                    "argument coercion skipped for %s",
                    getattr(message, "name", "?"),
                    exc_info=True,
                )
        return await call_next(context)
