"""Typed results for static analysis tools (issue #49, #111)."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, Field, model_serializer


class UnusedResourcesResult(BaseModel):
    unused: list[str] = Field(default_factory=list)
    scanned: int = 0
    referenced: int = 0


class SignalConnection(BaseModel):
    scene: str
    signal: str
    # 'from'/'to' are reserved-ish; the addon/analysis emit these keys directly.
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    method: str

    model_config = {"populate_by_name": True}

    @model_serializer(mode="wrap")
    def _serialize_with_wire_aliases(self, nxt: Any) -> dict[str, Any]:
        # FastMCP 4.0.0b2+ serializes structured tool output with `by_alias=False`
        # (`_serialize_to_jsonable` -> `TypeAdapter.dump_python(data, mode="json")`),
        # which drops Pydantic `Field(alias=...)` from the wire. The
        # `analyze_signal_flow` tool contract documents the keys as
        # `{scene, signal, from, to, method}` (issue #353 regression), so a wrap
        # serializer remaps the snake_case field names to the aliases regardless
        # of the `by_alias` flag FastMCP passes. When `by_alias=True` the keys
        # are already the aliases, so the guards skip.
        d = cast("dict[str, Any]", nxt(self))
        if "from_node" in d:
            d["from"] = d.pop("from_node")
        if "to_node" in d:
            d["to"] = d.pop("to_node")
        return d


class SignalFlowResult(BaseModel):
    connections: list[SignalConnection] = Field(default_factory=list)
    count: int = 0


class CircularDependenciesResult(BaseModel):
    cycles: list[list[str]] = Field(default_factory=list)
    count: int = 0


class SceneNodeCount(BaseModel):
    scene: str
    nodes: int


class ProjectStatsResult(BaseModel):
    scenes: int = 0
    scripts: int = 0
    resources: int = 0
    total_nodes: int = 0
    connections: int = 0
    by_extension: dict[str, int] = Field(default_factory=dict)
    busiest_scenes: list[SceneNodeCount] = Field(default_factory=list)


class ProjectStructureResult(BaseModel):
    """Raw project inventory (issue #210): ``res://`` paths bucketed by kind, plus
    the entry points. ``scenes``/``scripts``/``resources`` are sorted and
    non-overlapping; ``entry_points`` is a labelled cross-cut (main scene, autoloads,
    plugins)."""

    scenes: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Issue #111 — asset dependency, orphan detection, scene integrity
# ---------------------------------------------------------------------------


class AnalyzeDependenciesResult(BaseModel):
    path: str
    type: str = ""
    references: list[str] = Field(default_factory=list)
    referencers: list[str] = Field(default_factory=list)


class OrphanedResource(BaseModel):
    path: str
    type: str = ""
    estimated_size: int = 0


class FindOrphanedResult(BaseModel):
    orphaned: list[OrphanedResource] = Field(default_factory=list)
    scanned: int = 0


class IntegrityIssue(BaseModel):
    severity: str = "error"
    message: str
    node_path: str = ""
    property: str = ""


class ValidateSceneIntegrityResult(BaseModel):
    valid: bool = True
    errors: list[IntegrityIssue] = Field(default_factory=list)
    warnings: list[IntegrityIssue] = Field(default_factory=list)


class CrossSceneRefsResult(BaseModel):
    scenes: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
