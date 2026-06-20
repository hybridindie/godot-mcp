"""Typed results for script read/patch tools (issue #10)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScriptContent(BaseModel):
    script_path: str
    content: str


class ScriptList(BaseModel):
    directory: str
    scripts: list[str] = Field(default_factory=list)


class NodeScript(BaseModel):
    node_path: str
    script_path: str | None = None
    content: str | None = None


class WriteScriptResult(BaseModel):
    script_path: str
    created: bool = False
    # True when the write replaced an existing script (so the agent isn't blind to
    # clobbering hand-written code). In dry_run this is determined by an existence
    # probe; the change stays reversible via the editor's undo (#205).
    would_overwrite: bool = False
    dry_run: bool = False


class PatchScriptResult(BaseModel):
    script_path: str
    replacements: int = 0
    dry_run: bool = False


class ParseError(BaseModel):
    message: str
    source: str | None = None  # res:// path of the offending script
    line: int | None = None


class ParseCheckResult(BaseModel):
    script_path: str
    ok: bool
    errors: list[ParseError] = Field(default_factory=list)
