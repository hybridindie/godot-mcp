"""Typed results for runtime inspection tools (issue #35)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.json_strict import JSONBool, JSONFloat, JSONInt, JSONStr


class MonitorResult(BaseModel):
    monitoring: JSONBool
    node_path: JSONStr
    property: JSONStr
    samples: JSONInt = 0
    # #536 push-on-change sampling: only changed values are queued (default);
    # epsilon is the float-comparison tolerance for the change test.
    on_change_only: JSONBool = True
    epsilon: float = 0.0001


class PropertySample(BaseModel):
    frame: JSONInt
    value: Any = None


class PropertySamplesResult(BaseModel):
    ready: JSONBool = False
    connected: JSONBool = False
    node_path: JSONStr = ""
    property: JSONStr = ""
    samples: list[PropertySample] = Field(default_factory=list)
    error: JSONStr = ""
    # #459: stable reason token while pending (capture_pending).
    reason: str | None = None


class ReadPropertyResult(BaseModel):
    """One-shot live property read (#571): the value now, from the probe's
    dedicated read path that never touches the monitor slot."""

    ready: JSONBool = False
    node_path: JSONStr = ""
    property: JSONStr = ""
    value: Any = None
    error: JSONStr = ""
    # #459: stable reason token while pending (read_pending).
    reason: str | None = None


class Rect(BaseModel):
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class UiElement(BaseModel):
    path: JSONStr
    name: JSONStr
    node_class: JSONStr = ""
    visible: JSONBool = False
    rect: Rect = Field(default_factory=Rect)
    text: JSONStr = ""


class UiElementsResult(BaseModel):
    ready: JSONBool = False
    elements: list[UiElement] = Field(default_factory=list)
    # #459: stable reason token while pending (scan_in_flight).
    reason: str | None = None


class VelocityAtPointResult(BaseModel):
    """Velocity at an arbitrary point on a live RigidBody (Godot 4.8+, #599)."""

    ready: JSONBool = False
    node_path: JSONStr = ""
    node_class: JSONStr = ""
    dimension: JSONStr = ""  # "2d" | "3d", derived from the live body
    local: JSONBool = False  # true → get_velocity_at_local_position
    # JSON-safe vector shapes from type_coerce.gd ({x,y[,z]}), Any-typed so a
    # NaN/±INF sentinel string from the coercion layer is not shape drift.
    point: dict[str, Any] = Field(default_factory=dict)
    velocity: dict[str, Any] = Field(default_factory=dict)
    error: JSONStr = ""
    # #459: stable reason token while pending (velocity_pending).
    reason: str | None = None


class PhysicsQueryHit(BaseModel):
    """One collision record from a ``*_into`` space-state query (#599).

    Fields are method-dependent and absent ones keep their defaults: ray hits
    carry ``position``/``normal``/``face_index``; point/shape intersections carry
    the collider fields; ``collide_shape`` carries the point pair; ``get_rest_info``
    carries ``position``/``normal``/``collider_velocity``.
    """

    collider_path: JSONStr = ""
    collider_class: JSONStr = ""
    collider_id: JSONInt = 0
    # RIDs are not JSON values; the probe reports the numeric RID id.
    collider_rid: JSONInt = 0
    shape: JSONInt = 0
    position: dict[str, Any] = Field(default_factory=dict)
    normal: dict[str, Any] = Field(default_factory=dict)
    face_index: JSONInt = -1
    collider_velocity: dict[str, Any] = Field(default_factory=dict)
    point_on_queried_shape: dict[str, Any] = Field(default_factory=dict)
    point_on_colliding_shape: dict[str, Any] = Field(default_factory=dict)


class PhysicsSpaceQueryResult(BaseModel):
    """A non-allocating ``PhysicsDirectSpaceState2D/3D.*_into`` query (#599).

    ``hit`` is the method's own boolean; ``count`` is the number of records
    written into the preallocated result object (``max_results`` bounds it).
    """

    ready: JSONBool = False
    method: JSONStr = ""
    dimension: JSONStr = ""
    hit: JSONBool = False
    count: JSONInt = 0
    results: list[PhysicsQueryHit] = Field(default_factory=list)
    # cast_motion only (both default to 1.0 = the whole motion is safe).
    safe_fraction: JSONFloat | None = None
    unsafe_fraction: JSONFloat | None = None
    error: JSONStr = ""
    # #459: stable reason token while pending (query_pending).
    reason: str | None = None
