"""Animation tools (issue #39).

Author AnimationPlayer animations (tracks + keyframes) and AnimationTree graphs
(state machines / blend trees). Gated `animation` toolset; all `mutating`
(UndoRedo-wrapped addon-side) with `dry_run`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.categories import ANIMATION_TAG
from mcp_server.defaults import (
    DEFAULT_ANIMATION_EASING,
    DEFAULT_ANIMATION_LENGTH,
    DEFAULT_ANIMATION_TRACK_TYPE,
    DEFAULT_ANIMATION_TREE_NAME,
    DEFAULT_ANIMATION_TREE_ROOT_TYPE,
)
from mcp_server.models.animation import (
    AnimationDetail,
    AnimationList,
    AnimationTrackResult,
    AnimationTreeResult,
    BlendTreeNodeResult,
    CreateAnimationResult,
    KeyframeResult,
    StateMachineStateResult,
)
from mcp_server.safety import MUTATING, READ_ONLY, enforce_preconditions, require_node_exists
from mcp_server.tools._route import route, run_or_preview

ANIMATION = {ANIMATION_TAG}


def register_animation(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the animation tools."""

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def create_animation(
        node_path: str, name: str, length: float = DEFAULT_ANIMATION_LENGTH, dry_run: bool = False
    ) -> CreateAnimationResult:
        """Create an empty animation ``name`` (seconds ``length``) in the
        AnimationPlayer at ``node_path`` (adds a default library if needed).
        """
        await require_node_exists(bridge, node_path)
        params = {"node_path": node_path, "name": name, "length": length}
        preview = {"player_path": node_path, "animation": name, "length": length}
        return await run_or_preview(
            dry_run, CreateAnimationResult, preview, bridge, "cmd_create_animation", params
        )

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def add_animation_track(
        node_path: str,
        animation: str,
        track_path: str,
        track_type: str = DEFAULT_ANIMATION_TRACK_TYPE,
        dry_run: bool = False,
    ) -> AnimationTrackResult:
        """Add a track to ``animation`` targeting ``track_path`` (e.g.
        "Sprite2D:position"). ``track_type`` one of value/position_3d/rotation_3d/
        scale_3d/method/bezier/audio/animation. Returns the track index.
        """
        await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "animation": animation,
            "track_path": track_path,
            "track_type": track_type,
        }
        preview = {"animation": animation, "track_path": track_path}
        return await run_or_preview(
            dry_run, AnimationTrackResult, preview, bridge, "cmd_add_animation_track", params
        )

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def insert_keyframe(
        node_path: str,
        animation: str,
        track: int,
        time: float,
        value: Any,
        easing: float = DEFAULT_ANIMATION_EASING,
        dry_run: bool = False,
    ) -> KeyframeResult:
        """Insert a keyframe on ``track`` at ``time`` with ``value`` (Godot string
        forms like "Vector2(10, 20)" are accepted). ``easing`` is the key transition.
        ``value`` accepts JSON for the target Godot type — Vector2/3 as
        ``{"x":1,"y":2}``/``[1,2]``, Color as ``{"r":1,"g":0,"b":0,"a":1}`` or
        ``"#ff0000"``, Rect2 as ``{"position":{...},"size":{...}}``, NodePath/StringName
        as a string, primitives as-is. See docs/tool-contracts.md#value-shapes.
        """
        await require_node_exists(bridge, node_path)
        params = {
            "node_path": node_path,
            "animation": animation,
            "track": track,
            "time": time,
            "value": value,
            "easing": easing,
        }
        preview = {"animation": animation, "track": track, "time": time}
        return await run_or_preview(
            dry_run, KeyframeResult, preview, bridge, "cmd_insert_keyframe", params
        )

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def create_animation_tree(
        parent_path: str,
        name: str = DEFAULT_ANIMATION_TREE_NAME,
        anim_player: str = "",
        root_type: str = DEFAULT_ANIMATION_TREE_ROOT_TYPE,
        dry_run: bool = False,
    ) -> AnimationTreeResult:
        """Create an AnimationTree under ``parent_path`` with a ``root_type`` root
        (AnimationNodeStateMachine / AnimationNodeBlendTree) and optional
        ``anim_player`` path to the driving AnimationPlayer.
        """
        await require_node_exists(bridge, parent_path)
        preview = name if parent_path in (".", "") else f"{parent_path}/{name}"
        params: dict[str, Any] = {"parent_path": parent_path, "name": name, "root_type": root_type}
        if anim_player:
            params["anim_player"] = anim_player
        return await run_or_preview(
            dry_run,
            AnimationTreeResult,
            {"node_path": preview, "root_type": root_type},
            bridge,
            "cmd_create_animation_tree",
            params,
        )

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def add_state_machine_state(
        tree_path: str, state_name: str, animation: str = "", dry_run: bool = False
    ) -> StateMachineStateResult:
        """Add a state ``state_name`` (playing ``animation`` if given) to the
        AnimationTree's state-machine root at ``tree_path``.
        """
        await require_node_exists(bridge, tree_path)
        params: dict[str, Any] = {"tree_path": tree_path, "state_name": state_name}
        if animation:
            params["animation"] = animation
        preview = {"tree_path": tree_path, "state": state_name}
        return await run_or_preview(
            dry_run, StateMachineStateResult, preview, bridge, "cmd_add_state_machine_state", params
        )

    @mcp.tool(meta=MUTATING, tags=ANIMATION)
    @enforce_preconditions
    async def set_blend_tree_node(
        tree_path: str, node_name: str, node_type: str, dry_run: bool = False
    ) -> BlendTreeNodeResult:
        """Add an AnimationNode (``node_type``, e.g. AnimationNodeAnimation) named
        ``node_name`` to the AnimationTree's blend-tree root at ``tree_path``.
        """
        await require_node_exists(bridge, tree_path)
        params = {"tree_path": tree_path, "node_name": node_name, "node_type": node_type}
        preview = {"tree_path": tree_path, "node": node_name, "node_type": node_type}
        return await run_or_preview(
            dry_run, BlendTreeNodeResult, preview, bridge, "cmd_set_blend_tree_node", params
        )

    @mcp.tool(meta=READ_ONLY, tags=ANIMATION)
    async def list_animations(node_path: str) -> AnimationList:
        """List the animation names on the AnimationPlayer at ``node_path``. Pair with
        ``get_animation`` to snapshot an animation before editing it — for rollback.
        Errors if the node isn't an AnimationPlayer or doesn't resolve.
        """
        return AnimationList(**await route(bridge, "cmd_list_animations", {"node_path": node_path}))

    @mcp.tool(meta=READ_ONLY, tags=ANIMATION)
    async def get_animation(node_path: str, animation_name: str) -> AnimationDetail:
        """Read an animation on the AnimationPlayer at ``node_path``: its ``length`` and
        each ``track`` ({type, path, keys:[{time, value}]}), with keyframe values
        JSON-coerced (Vector2 as {"x","y"}, …). The inverse of the animation writers
        (create_animation / add_animation_track / insert_keyframe) — capture this before
        a change to roll it back. Errors RESOURCE_NOT_FOUND if the animation is absent.
        """
        params = {"node_path": node_path, "animation_name": animation_name}
        return AnimationDetail(**await route(bridge, "cmd_get_animation", params))
