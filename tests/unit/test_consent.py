"""Unit: consent tokens bind exact destructive args (#759)."""

from __future__ import annotations

import pytest

from mcp_server.consent import ConsentError, ConsentManager, canonical_args


def _manager(clock: list[float], ttl: float = 120.0) -> ConsentManager:
    return ConsentManager(secret=b"unit-test-secret", ttl_seconds=ttl, clock=lambda: clock[0])


def test_mint_and_verify_roundtrip_ignores_confirm_and_consent() -> None:
    clock = [1_000.0]
    manager = _manager(clock)
    token, expires_at = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    assert expires_at == 1_120.0
    manager.verify(
        "godot_scene_edit_delete_node",
        {"node_path": "A", "confirm": True, "consent": "ignored"},
        token,
    )


def test_changed_args_are_refused() -> None:
    clock = [1_000.0]
    manager = _manager(clock)
    token, _ = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    with pytest.raises(ConsentError) as exc:
        manager.verify("godot_scene_edit_delete_node", {"node_path": "B"}, token)
    assert exc.value.reason == "args"


def test_other_tool_is_refused() -> None:
    clock = [1_000.0]
    manager = _manager(clock)
    token, _ = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    with pytest.raises(ConsentError) as exc:
        manager.verify("godot_scene_edit_move_node", {"node_path": "A"}, token)
    assert exc.value.reason == "tool"


def test_expired_token_is_refused() -> None:
    clock = [1_000.0]
    manager = _manager(clock, ttl=10.0)
    token, _ = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    clock[0] = 1_011.0
    with pytest.raises(ConsentError) as exc:
        manager.verify("godot_scene_edit_delete_node", {"node_path": "A"}, token)
    assert exc.value.reason == "expired"


def test_replayed_token_is_refused() -> None:
    clock = [1_000.0]
    manager = _manager(clock)
    token, _ = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    manager.verify("godot_scene_edit_delete_node", {"node_path": "A"}, token)
    with pytest.raises(ConsentError) as exc:
        manager.verify("godot_scene_edit_delete_node", {"node_path": "A"}, token)
    assert exc.value.reason == "replayed"


def test_tampered_token_is_refused() -> None:
    clock = [1_000.0]
    manager = _manager(clock)
    token, _ = manager.mint("godot_scene_edit_delete_node", {"node_path": "A"})
    body, signature = token.rsplit(".", 1)
    tampered = body + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(ConsentError) as exc:
        manager.verify("godot_scene_edit_delete_node", {"node_path": "A"}, tampered)
    assert exc.value.reason == "signature"


def test_canonical_args_is_stable() -> None:
    assert canonical_args({"b": 2, "a": 1}) == canonical_args({"a": 1, "b": 2})
    assert canonical_args({"a": 1, "confirm": True}) == canonical_args({"a": 1})
