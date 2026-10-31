"""Sub-command policy for the ``run_commands`` batch (issue #634).

``godot_composite_run_commands`` forwards arbitrary ``cmd_*`` entries to the addon
in one round-trip. The outer tool is tagged ``mutating``, so without this module a
single batch could run **destructive** commands without ``confirm``, reach
commands whose toolset is gated off, and skip the server's per-command path
preflight — breaking the rule that safety lives in the server
(``.claude/rules/mcp-tools.md``, ``.claude/rules/architecture.md``).

This module is the single source of truth for a sub-command's policy. Every
entry is resolved back to the exposed tool that backs it (the registry is the
authority; the static ``command_map.BARE_TO_COMMAND`` table is only the
reverse-index used to find the tool), and the tool's own ``safety_class`` and
toolset are read from it — never trusted from the ``cmd_*`` string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from mcp_server.categories import CORE_TAG
from mcp_server.command_map import BARE_TO_COMMAND, resolve_command
from mcp_server.models.run_commands import SubCommandPlan
from mcp_server.safety import SafetyClass, require_confirmation
from mcp_server.tools._route import validate_or_raise
from mcp_server.transforms import _original_handler_name

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.tools.base import Tool

    from mcp_server.bridge import Bridge

# The original handler name (not the transformed ``godot_…`` name) of the tool
# whose arguments are sub-commands. `_original_handler_name` on the registered
# ``Tool`` yields this, so the middleware keys off the handler, not a name string.
BATCH_HANDLER = "run_commands"

# ``cmd_*`` -> exposed bare name (the exposed tool name minus ``godot_``), derived
# from the registry-mirrored table. First writer wins; the drift test in
# tests/unit/test_command_map.py pins the table against the live registry.
COMMAND_TO_BARE: dict[str, str] = {}
for _bare, _command in BARE_TO_COMMAND.items():
    COMMAND_TO_BARE.setdefault(_command, _bare)


def toolset_of(tags: Any) -> str:
    """A tool's gating category: its single non-core tag, or ``core``."""
    non_core = sorted(t for t in (tags or ()) if t != CORE_TAG)
    return non_core[0] if non_core else CORE_TAG


async def resolve_subcommand(mcp: FastMCP, command: str) -> SubCommandPlan:
    """Resolve a normalized ``cmd_*`` to the exposed tool that backs it.

    Returns a plan with ``tool=None`` when the command maps to no registered
    tool (an unknown ``cmd_*``). The registry is queried by the derived exposed
    name so disabled toolsets resolve too (their visibility is checked
    separately).
    """
    bare = COMMAND_TO_BARE.get(command)
    tool_name = f"godot_{bare}" if bare else None
    tool: Tool | None = None
    if tool_name is not None:
        try:
            tool = await mcp.get_tool(tool_name)
        except Exception:
            tool = None
    if tool is None:
        return SubCommandPlan(command=command, tool=None)
    return SubCommandPlan(
        command=command,
        tool=tool_name,
        toolset=toolset_of(getattr(tool, "tags", set())),
        safety_class=(tool.meta or {}).get("safety_class"),
    )


async def resolve_batch(mcp: FastMCP, commands: list[dict[str, Any]]) -> list[SubCommandPlan]:
    """Resolve every entry of a batch; an unresolvable name yields ``tool=None``."""
    plans: list[SubCommandPlan] = []
    for entry in commands:
        raw = str(entry.get("command", ""))
        try:
            command = resolve_command(raw)
        except ToolError:
            plans.append(SubCommandPlan(command=raw, tool=None))
            continue
        plans.append(await resolve_subcommand(mcp, command))
    return plans


async def guard_batch(
    mcp: FastMCP,
    bridge: Bridge,
    enabled: set[str],
    commands: list[dict[str, Any]],
    *,
    confirm: bool,
    dry_run: bool,
) -> list[SubCommandPlan]:
    """Enforce per-sub-command safety; raise a structured ``ToolError``/precondition.

    For each entry: refuse an unknown ``cmd_*``, a command from a disabled
    toolset, a destructive command without ``confirm`` (skipped on a preview),
    and any command whose params fail the server path preflight. Returns the
    resolved plans so the caller can report them (and stamp them on a preview).

    ``commands`` are already normalized to the addon ``cmd_*`` form by the
    caller. ``confirm`` is only enforced on a real run — a ``dry_run`` previews.
    """
    plans: list[SubCommandPlan] = []
    for entry in commands:
        command = str(entry.get("command", ""))
        params = entry.get("params", {}) or {}
        plan = await resolve_subcommand(mcp, command)
        if plan.tool is None:
            raise ToolError(
                f"VALIDATION_ERROR: unknown command '{command}' in the batch — it backs "
                "no registered tool. Use an exposed tool name (e.g. "
                "'scene_edit_create_node') or its cmd_* form."
            )
        if plan.toolset != CORE_TAG and plan.toolset not in enabled:
            raise ToolError(
                f"Tool '{plan.tool}' is not enabled. Call godot_list_toolsets() to see "
                f"available toolsets, then godot_enable_toolset('{plan.toolset}') to "
                "expose its tools before batching them."
            )
        if not dry_run and plan.safety_class == SafetyClass.DESTRUCTIVE.value:
            require_confirmation(confirm, f"run_commands (contains destructive '{command}')")
        await validate_or_raise(bridge, command, params)
        plans.append(plan)
    return plans


def _most_severe(base: str, plans: list[SubCommandPlan]) -> str:
    """Escalate ``base`` by the safety classes present among ``plans``."""
    classes = {base} | {p.safety_class for p in plans if p.safety_class}
    for candidate in (SafetyClass.DESTRUCTIVE, SafetyClass.MUTATING, SafetyClass.RUNTIME):
        if candidate.value in classes:
            return candidate.value
    return base


async def mutating_commands(mcp: FastMCP) -> frozenset[str]:
    """Every addon ``cmd_*`` backed by a mutating/destructive tool (issue #644).

    Used to flag a TIMEOUT on such a command ``may_have_applied`` — the editor
    drains commands serially, so a timed-out mutation can still run later. Reads
    the registry directly (the ``godot_`` transform may not be installed yet).
    """
    from mcp_server.command_map import BARE_TO_COMMAND
    from mcp_server.transforms import _original_handler_name, godot_tool_name

    out: set[str] = set()
    for tool in await mcp.local_provider.list_tools():
        if (tool.meta or {}).get("safety_class") not in (
            SafetyClass.MUTATING.value,
            SafetyClass.DESTRUCTIVE.value,
        ):
            continue
        bare = godot_tool_name(_original_handler_name(tool), tool.tags).removeprefix("godot_")
        command = BARE_TO_COMMAND.get(bare)
        if command:
            out.add(command)
    return frozenset(out)


async def effective_safety_class(mcp: FastMCP, tool: Tool, args: dict[str, Any]) -> str:
    """The safety class the approval gate should use for a tool call.

    For every tool this is its own ``safety_class`` meta. For the batch tool it
    is escalated to the most severe class among its sub-commands, so a batch
    containing a destructive entry is approved as destructive (issue #634).
    Resolution failure never breaks approval — it falls back to the tool's own
    class, and the tool body still refuses an unresolvable entry.
    """
    base = (tool.meta or {}).get("safety_class") or ""
    if _original_handler_name(tool) != BATCH_HANDLER:
        return base
    commands = args.get("commands") or []
    try:
        plans = await resolve_batch(mcp, commands)
    except Exception:
        return base
    return _most_severe(base, plans)


__all__ = [
    "BATCH_HANDLER",
    "COMMAND_TO_BARE",
    "effective_safety_class",
    "guard_batch",
    "mutating_commands",
    "resolve_batch",
    "resolve_subcommand",
    "toolset_of",
]
