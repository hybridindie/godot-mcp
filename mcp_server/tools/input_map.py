"""Input map editing tools (issue #81).

Author the project's Input Map: add/remove actions, add events to actions,
and clear events. Persisted via ProjectSettings 'input/<action>' + save().
All in the `input_map` toolset (gated off by default).
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import INPUT_MAP_TAG
from mcp_server.defaults import (
    DEFAULT_INPUT_AXIS_VALUE,
    DEFAULT_INPUT_DEADZONE,
)
from mcp_server.models.input_map import (
    AddInputActionResult,
    AddInputEventResult,
    ClearInputActionEventsResult,
    InputActionEvents,
    RemoveInputActionResult,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    READ_ONLY,
    ApprovalGate,
    enforce_preconditions,
    require_bridge_connected,
    require_confirmation,
)
from mcp_server.tools._route import route, run_or_preview

INPUT_MAP = {INPUT_MAP_TAG}


def register_input_map(
    mcp: FastMCP, bridge: Bridge, approval: ApprovalGate | None = None
) -> None:
    """Register the input map editing tools."""
    approval = approval or ApprovalGate()

    @mcp.tool(meta=MUTATING, tags=INPUT_MAP)
    @enforce_preconditions
    async def add_input_action(
        name: str, deadzone: float = DEFAULT_INPUT_DEADZONE, dry_run: bool = False
    ) -> AddInputActionResult:
        """Add a new input action to the project Input Map.

        The action is persisted in ProjectSettings and saved to project.godot.
        Events for this action are added separately with ``add_input_event``.
        """
        require_bridge_connected(bridge)
        params = {"name": name, "deadzone": deadzone}
        preview = {"name": name, "added": False, "deadzone": deadzone}
        return await run_or_preview(
            dry_run, AddInputActionResult, preview, bridge, "cmd_add_input_action", params
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=INPUT_MAP)
    @enforce_preconditions
    async def remove_input_action(
        name: str, confirm: bool = False, dry_run: bool = False
    ) -> RemoveInputActionResult:
        """Remove an input action (and all its events) from the project Input Map.

        Destructive: requires ``confirm=True``.
        """
        require_bridge_connected(bridge)
        if not dry_run:
            require_confirmation(confirm, "remove_input_action")
            await approval.require("remove_input_action", "destructive", {"name": name})
        params = {"name": name, "confirm": True}
        preview = {"name": name, "removed": False}
        return await run_or_preview(
            dry_run, RemoveInputActionResult, preview, bridge, "cmd_remove_input_action", params
        )

    @mcp.tool(meta=MUTATING, tags=INPUT_MAP)
    @enforce_preconditions
    async def add_input_event(
        action: str,
        event_type: str,
        # key event
        keycode: str = "",
        physical_keycode: str = "",
        shift: bool = False,
        ctrl: bool = False,
        alt: bool = False,
        meta: bool = False,
        # mouse event
        button: str = "",
        # joypad event
        device: int = 0,
        axis: int = -1,
        axis_value: float = DEFAULT_INPUT_AXIS_VALUE,
        joy_button_index: int = -1,
        dry_run: bool = False,
    ) -> AddInputEventResult:
        """Add an input event to an existing input action.

        ``event_type`` is one of ``key``, ``mouse``, ``joypad_button``, ``joypad_motion``.
        For ``key``: set ``keycode`` or ``physical_keycode`` (a Godot Key name like
        ``"Space"`` or ``"A"``). For ``mouse``: set ``button`` (``left``, ``right``,
        ``middle``, ``wheel_up``, ``wheel_down``). For ``joypad_*``: set ``device``,
        ``joy_button_index`` (button events) or ``axis`` + ``axis_value`` (motion events).
        """
        require_bridge_connected(bridge)
        params: dict[str, object] = {
            "action": action,
            "event_type": event_type,
            "keycode": keycode,
            "physical_keycode": physical_keycode,
            "shift": shift,
            "ctrl": ctrl,
            "alt": alt,
            "meta": meta,
            "button": button,
            "device": device,
            "axis": axis,
            "axis_value": axis_value,
            "joy_button_index": joy_button_index,
        }
        preview = {"action": action, "added": False}
        return await run_or_preview(
            dry_run, AddInputEventResult, preview, bridge, "cmd_add_input_event", params
        )

    @mcp.tool(meta=DESTRUCTIVE, tags=INPUT_MAP)
    @enforce_preconditions
    async def clear_input_action_events(
        action: str, confirm: bool = False, dry_run: bool = False
    ) -> ClearInputActionEventsResult:
        """Remove all events from an input action, leaving the action itself intact.

        Destructive: requires ``confirm=True``.
        """
        require_bridge_connected(bridge)
        if not dry_run:
            require_confirmation(confirm, "clear_input_action_events")
            await approval.require("clear_input_action_events", "destructive", {"action": action})
        params = {"action": action, "confirm": True}
        preview = {"action": action, "cleared": False}
        return await run_or_preview(
            dry_run,
            ClearInputActionEventsResult,
            preview,
            bridge,
            "cmd_clear_input_action_events",
            params,
        )

    @mcp.tool(meta=READ_ONLY, tags=INPUT_MAP)
    async def get_input_action_events(action: str) -> InputActionEvents:
        """Read an input action's ``deadzone`` and full event list. Each event is a dict
        in the same shape ``add_input_event`` accepts (``event_type`` plus its
        kind-specific keys — ``keycode``/``physical_keycode``/modifiers for key,
        ``button`` for mouse, ``device``/``joy_button_index`` or ``axis``/``axis_value``
        for joypad). The inverse of ``add_input_event`` / ``clear_input_action_events`` /
        ``remove_input_action`` — snapshot an action before editing it so it can be
        rebuilt. Errors (RESOURCE_NOT_FOUND) if no such action exists.
        """
        require_bridge_connected(bridge)
        return InputActionEvents(
            **await route(bridge, "cmd_get_input_action_events", {"action": action})
        )
