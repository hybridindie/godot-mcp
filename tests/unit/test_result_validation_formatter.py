"""Unit tests for the #567 INTERNAL_ERROR formatter.

Pins the wire text of ``format_result_validation_error``: tool name, result
model, per-field paths/messages with truncated inputs, and the framing that
tells the agent the *addon payload* didn't match (not its own arguments).
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from mcp_server.result_validation_middleware import format_result_validation_error


class _Sample(BaseModel):
    count: int
    name: str


def _ve(**fields: object) -> ValidationError:
    try:
        _Sample(**fields)  # type: ignore[arg-type]
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_formatter_names_tool_model_field_msg_and_input() -> None:
    text = format_result_validation_error(
        "godot_describe_class", "ClassInfo", _ve(count="x", name="ok")
    )
    assert text.startswith("INTERNAL_ERROR:")
    assert "godot_describe_class" in text
    assert "ClassInfo" in text
    assert "count" in text
    assert "'x'" in text
    assert "not a parameter problem" in text


def test_formatter_truncates_huge_inputs() -> None:
    huge = "z" * 10_000
    text = format_result_validation_error("t", "M", _ve(count=huge, name="ok"))
    assert huge not in text  # truncated
    assert "z" * 20 in text  # a readable prefix survives


def test_formatter_lists_each_offending_field() -> None:
    text = format_result_validation_error("t", "M", _ve(count="bad", name=123))
    assert "count" in text and "name" in text
    assert "123" in text