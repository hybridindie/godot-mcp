"""Project-registered tools from annotated GDScript (#761).

The addon scans ``@tool`` scripts for functions marked with ``## @mcp_tool`` and
returns their signatures. This module turns each descriptor into a real MCP tool
under the gated ``project`` toolset, so a project's own operations are callable
by name instead of being reconstructed from generic node edits.

Library-first (see .claude/rules/architecture.md): the handler is delegation
only; safety (``dry_run``/``confirm``) is enforced here, never in the addon; the
addon owns discovery and execution.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast

from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool

from mcp_server.bridge import Bridge
from mcp_server.categories import PROJECT_TAG
from mcp_server.models.project_tools import (
    ProjectToolInfo,
    ProjectToolRejection,
    ProjectToolsResult,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    annotations_for_safety_class,
    enforce_preconditions,
    require_confirmation,
)
from mcp_server.tools._route import route

PROJECT = {PROJECT_TAG}
_SAFETY_META = {"read_only": READ_ONLY, "mutating": MUTATING, "destructive": DESTRUCTIVE}
_SLUG = re.compile(r"[^a-z0-9_]+")

SCAN_COMMAND = "cmd_scan_project_tools"
RUN_COMMAND = "cmd_run_project_tool"

logger = logging.getLogger(__name__)


def _slug(value: str) -> str:
    """Lowercase, punctuation → ``_`` — a stable MCP tool-name fragment."""
    return _SLUG.sub("_", value.lower()).strip("_") or "tool"


def _public_name(entry: dict[str, Any]) -> str:
    """``godot_`` + ``project_<script stem>_<function>`` (the exposed name)."""
    script = str(entry.get("script", ""))
    stem = script.rsplit("/", 1)[-1].removesuffix(".gd")
    function = str(entry.get("function") or entry.get("name") or "tool")
    return "_".join(("godot", "project", _slug(stem), _slug(function)))


def _with_safety_params(entry: dict[str, Any], safety: str) -> dict[str, Any]:
    """Copy the addon's JSON Schema and add the safety flags the class requires."""
    parameters = dict(entry.get("parameters") or {})
    properties = dict(parameters.get("properties") or {})
    if safety in ("mutating", "destructive"):
        properties["dry_run"] = {
            "type": "boolean",
            "default": False,
            "description": "Preview what would change without running the project tool.",
        }
    if safety == "destructive":
        properties["confirm"] = {
            "type": "boolean",
            "default": False,
            "description": "Required to run a destructive project tool.",
        }
    parameters["type"] = "object"
    parameters["properties"] = properties
    parameters.setdefault("additionalProperties", False)
    return parameters


def _description(entry: dict[str, Any], safety: str) -> str:
    text = str(entry.get("description") or "").strip()
    if not text:
        text = f"Project tool '{entry.get('function')}' from {entry.get('script')}."
    if safety == "destructive":
        text += " Destructive: requires confirm=True."
    elif safety == "mutating":
        text += " Mutating: supports dry_run=True."
    return text


def _build_tool(bridge: Bridge, entry: dict[str, Any]) -> FunctionTool:
    """Turn one addon descriptor into a callable, appropriately-tagged tool."""
    safety = str(entry.get("safety_class") or "mutating")
    if safety not in _SAFETY_META:
        safety = "mutating"
    name = _public_name(entry)
    script = str(entry.get("script", ""))
    function = str(entry.get("function", ""))

    @enforce_preconditions
    async def _run(**kwargs: Any) -> dict[str, Any]:
        dry_run = bool(kwargs.pop("dry_run", False))
        confirm = bool(kwargs.pop("confirm", False))
        if safety == "destructive" and not dry_run:
            require_confirmation(confirm, name)
        if dry_run:
            return {
                "dry_run": True,
                "preview": {"script": script, "function": function, "args": dict(kwargs)},
                "result": None,
            }
        return await route(
            bridge, RUN_COMMAND, {"script": script, "function": function, "args": kwargs}
        )

    # Keep the handler name equal to the public stem so a later transform pass
    # (godot_tool_name) resolves back to the same name instead of inventing one.
    _run.__name__ = name.removeprefix("godot_")
    return FunctionTool(
        fn=_run,
        name=name,
        description=_description(entry, safety),
        parameters=_with_safety_params(entry, safety),
        tags=PROJECT,
        meta=_SAFETY_META[safety],
        annotations=annotations_for_safety_class(safety),
    )


class ProjectToolRegistrar:
    """Registers, refreshes and replaces the project tools for one server."""

    def __init__(
        self,
        mcp: FastMCP,
        bridge: Bridge,
        hub: Any | None = None,
        *,
        debounce: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._mcp = mcp
        self._bridge = bridge
        self._hub = hub
        self._registered: set[str] = set()
        self._debounce = debounce
        self._sleep = sleep or asyncio.sleep
        self._pending = False
        self._task: asyncio.Task[None] | None = None

    def schedule_rescan(self) -> None:
        """Schedule one debounced rescan for a filesystem-change notice (#802).

        Called from the bridge read loop, so it must not block: it sets a flag
        and starts a task. Repeated notices during the debounce or the scan
        coalesce into a single follow-up pass.
        """
        self._pending = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._rescan_loop())

    async def _rescan_loop(self) -> None:
        while self._pending:
            self._pending = False
            await self._sleep(self._debounce)
            try:
                await self.scan()
            except Exception:
                # Keep the previous surface; a transient bridge failure must not
                # unregister tools the agent is mid-way through using.
                logger.warning(
                    "project-tool rescan failed; keeping the previous surface",
                    exc_info=True,
                )

    async def flush(self) -> None:
        """Await the in-flight debounce/rescan (tests and release checks)."""
        task = self._task
        if task is not None:
            await asyncio.shield(task)

    async def scan(self) -> ProjectToolsResult:
        payload = await route(self._bridge, SCAN_COMMAND, {})
        entries = list(payload.get("tools") or [])
        rejected = [ProjectToolRejection(**item) for item in payload.get("rejected") or []]

        # A re-scan replaces the previous surface: removed annotations disappear.
        for name in self._registered:
            try:
                self._mcp.local_provider.remove_tool(name)
            except KeyError:
                pass
        self._registered.clear()

        registered: list[ProjectToolInfo] = []
        seen: set[str] = set()
        for entry in entries:
            name = _public_name(entry)
            if name in seen:
                rejected.append(
                    ProjectToolRejection(
                        script=str(entry.get("script", "")),
                        function=entry.get("function"),
                        reason=f"duplicate tool name '{name}' (two scripts share a stem)",
                    )
                )
                continue
            seen.add(name)
            tool = _build_tool(self._bridge, entry)
            self._mcp.add_tool(tool)
            self._registered.add(name)
            registered.append(
                ProjectToolInfo(
                    name=name,
                    script=str(entry.get("script", "")),
                    function=str(entry.get("function", "")),
                    safety_class=cast(
                        "Literal['read_only', 'mutating', 'destructive']",
                        str(entry.get("safety_class") or "mutating"),
                    ),
                    description=str(entry.get("description") or ""),
                )
            )

        if self._hub is not None:
            await self._hub.publish_tools_changed()
        return ProjectToolsResult(registered=registered, rejected=rejected)


def register_project_tools(mcp: FastMCP, bridge: Bridge, hub: Any | None = None) -> None:
    """Register the project-tool scanner in the gated ``project`` toolset."""
    registrar = ProjectToolRegistrar(mcp, bridge, hub)
    # #802: the addon sends a debounced notice when the project filesystem changes.
    bridge.on_project_tools_changed = registrar.schedule_rescan

    @mcp.tool(meta=READ_ONLY, tags=PROJECT)
    @enforce_preconditions
    async def project_scan_tools() -> ProjectToolsResult:
        """Scan ``res://`` for ``## @mcp_tool`` functions and register each in this
        ``project`` toolset (re-scan replaces the set). Returns ``registered`` +
        ``rejected``; a rejection is partial success. Scripts extend ``RefCounted``
        and own their undo.
        """
        return await registrar.scan()


__all__ = ["ProjectToolRegistrar", "register_project_tools"]
