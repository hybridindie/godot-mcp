"""Typed results for resource-file + autoload tools (issue #34)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.receipt import ChangeReceipt


class ResourceContent(BaseModel):
    resource_path: str
    type: str
    script: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class CreateResourceResult(BaseModel):
    resource_path: str
    type: str
    created: bool = False
    dry_run: bool = False
    hint: str | None = None
    receipt: ChangeReceipt | None = None
    reversible_by: Literal["undo", "vcs", "none"] = "none"


class SetResourcePropertyResult(BaseModel):
    resource_path: str
    property: str
    value: Any = None
    set: bool = False
    dry_run: bool = False
    hint: str | None = None
    receipt: ChangeReceipt | None = None
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class RegisterAutoloadResult(BaseModel):
    name: str
    path: str
    registered: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"


class UnregisterAutoloadResult(BaseModel):
    name: str
    unregistered: bool = False
    dry_run: bool = False
    reversible_by: Literal["undo", "vcs", "none"] = "undo"
