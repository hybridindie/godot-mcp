"""Typed results for script read/patch tools (issue #10)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_serializer


class ScriptContent(BaseModel):
    script_path: str
    content: str


class ScriptList(BaseModel):
    directory: str
    scripts: list[str] = Field(default_factory=list)
    # Pagination (issue #222): ``scripts`` is a page of ``total`` files.
    total: int = 0
    returned: int = 0
    truncated: bool = False
    next_offset: int | None = None


class NodeScript(BaseModel):
    node_path: str
    script_path: str | None = None
    content: str | None = None


class WriteScriptResult(BaseModel):
    script_path: str
    created: bool = False
    # Real-run truth about what the write did (#424): an overwrite reports
    # ``overwrote=True, previous_existed=True`` — the response must never read like
    # a no-op while the bytes landed. In dry_run the effect hasn't happened, so the
    # result instead carries ``would_overwrite`` from the existence probe; the
    # change stays reversible via the editor's undo (#205).
    overwrote: bool = False
    previous_existed: bool = False
    would_overwrite: bool = False
    dry_run: bool = False

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, Any]:
        # Mode-split serialization (same pattern as UndoResult): a real run never
        # carries the dry-run probe key ``would_overwrite`` (it reads like a no-op,
        # #424), and a dry-run preview never carries the effect keys. FastMCP builds
        # structured_content via pydantic-core, which only honors this hook.
        data = {"script_path": self.script_path, "created": self.created}
        if self.dry_run:
            data["dry_run"] = True
            data["would_overwrite"] = self.would_overwrite
            data["previous_existed"] = self.previous_existed
        else:
            data["overwrote"] = self.overwrote
            data["previous_existed"] = self.previous_existed
        return data


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
