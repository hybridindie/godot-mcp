"""Typed results for the core ``godot_describe_class`` tool (#533).

ClassDB metadata for agent discovery — properties, methods, signals,
constants, enums, the inheritance chain, and instantiability. Every ``type``
field is a Variant.Type *name*: the exact token the addon's JSON coercion
layer accepts shapes for.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ClassProperty(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    type: str
    default: str


class ClassArgument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    type: str


class ClassMethod(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    args: list[ClassArgument]
    return_type: str


class ClassSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    args: list[ClassArgument]


class ClassConstant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: int
    enum: str


class ClassEnum(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    members: list[str]


class ClassInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_name: str
    inherits: str
    inherits_chain: list[str]
    can_instantiate: bool
    properties: list[ClassProperty]
    methods: list[ClassMethod]
    signals: list[ClassSignal]
    constants: list[ClassConstant]
    enums: list[ClassEnum]