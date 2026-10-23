"""Typed results for resource-file + autoload tools (issue #34)."""

from __future__ import annotations

from typing import Any

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


class SetResourcePropertyResult(BaseModel):
    resource_path: str
    property: str
    value: Any = None
    set: bool = False
    dry_run: bool = False
    hint: str | None = None
    receipt: ChangeReceipt | None = None


class RegisterAutoloadResult(BaseModel):
    name: str
    path: str
    registered: bool = False
    dry_run: bool = False


class UnregisterAutoloadResult(BaseModel):
    name: str
    unregistered: bool = False
    dry_run: bool = False
