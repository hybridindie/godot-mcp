"""Typed results for export tools (issue #50)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mcp_server.models.runtime import LogEntry


class ExportPreset(BaseModel):
    index: int = 0
    name: str
    platform: str = ""
    runnable: bool = False
    export_path: str = ""


class ExportPresetsResult(BaseModel):
    presets: list[ExportPreset] = Field(default_factory=list)
    has_config: bool = False


class ExportInfoResult(BaseModel):
    has_config: bool = False
    preset_count: int = 0
    preset_names: list[str] = Field(default_factory=list)
    config_path: str = ""


class ExportResult(BaseModel):
    exported: bool = False
    preset: str = ""
    output_path: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float = 0.0
    errors: list[LogEntry] = Field(default_factory=list)
    warnings: list[LogEntry] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
