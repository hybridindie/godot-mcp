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
    RemoveInputActionResult,
)
from mcp_server.safety import (
    DESTRUCTIVE,
    MUTATING,
    enforce_preconditions,
    require_bridge_connected,
    require_confirmation,
)
from mcp_server.tools._route import route

INPUT_MAP = {INPUT_MAP_TAG}


def register_input_map(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the input map editing tools."""

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
        if dry_run:
            return AddInputActionResult(name=name, added=False, deadzone=deadzone, dry_run=True)
        params = {"name": name, "deadzone": deadzone}
        return AddInputActionResult(**await route(bridge, "cmd_add_input_action", params))

    @mcp.tool(meta=DESTRUCTIVE, tags=INPUT_MAP)
    @enforce_preconditions
    async def remove_input_action(
        name: str, confirm: bool = False, dry_run: bool = False
    ) -> RemoveInputActionResult:
        """Remove an input action (and all its events) from the project Input Map.

        Destructive: requires ``confirm=True``.
        """
        require_bridge_connected(bridge)
        if dry_run:
            return RemoveInputActionResult(name=name, removed=False, dry_run=True)
        require_confirmation(confirm, "remove_input_action")
        params = {"name": name, "confirm": True}
        return RemoveInputActionResult(**await route(bridge, "cmd_remove_input_action", params))

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
        if dry_run:
            return AddInputEventResult(action=action, added=False, dry_run=True)
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
        return AddInputEventResult(**await route(bridge, "cmd_add_input_event", params))

    @mcp.tool(meta=DESTRUCTIVE, tags=INPUT_MAP)
    @enforce_preconditions
    async def clear_input_action_events(
        action: str, confirm: bool = False, dry_run: bool = False
    ) -> ClearInputActionEventsResult:
        """Remove all events from an input action, leaving the action itself intact.

        Destructive: requires ``confirm=True``.
        """
        require_bridge_connected(bridge)
        if dry_run:
            return ClearInputActionEventsResult(action=action, cleared=False, dry_run=True)
        require_confirmation(confirm, "clear_input_action_events")
        params = {"action": action, "confirm": True}
        return ClearInputActionEventsResult(
            **await route(bridge, "cmd_clear_input_action_events", params)
        )
