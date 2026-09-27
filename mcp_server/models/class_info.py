"""Typed results for the core ``godot_describe_class`` tool (#533).

ClassDB metadata for agent discovery — properties, methods, signals,
constants, enums, the inheritance chain, and instantiability. Every ``type``
field is a Variant.Type *name*: the exact token the addon's JSON coercion
layer accepts shapes for.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from mcp_server.models.json_strict import JSONBool, JSONInt, JSONStr


class ClassProperty(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    type: JSONStr
    # #564: the addon sends Coerce.to_json's JSON-safe Variant (a dict for
    # Vector2/Color/Rect2, raw int/float/bool otherwise, null when ClassDB
    # stores no default) — never a string. Any keeps the structured shape,
    # which is the shape the coercion layer accepts back for set_node_property.
    default: Any


class ClassArgument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    type: JSONStr


class ClassMethod(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    args: list[ClassArgument]
    return_type: JSONStr


class ClassSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    args: list[ClassArgument]


class ClassConstant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    value: JSONInt
    enum: JSONStr


class ClassEnum(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: JSONStr
    members: list[JSONStr]


class ClassInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_name: JSONStr
    inherits: JSONStr
    inherits_chain: list[JSONStr]
    can_instantiate: JSONBool
    properties: list[ClassProperty]
    methods: list[ClassMethod]
    signals: list[ClassSignal]
    constants: list[ClassConstant]
    enums: list[ClassEnum]