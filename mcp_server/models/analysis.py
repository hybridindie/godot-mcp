"""Typed results for static analysis tools (issue #49, #111)."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
