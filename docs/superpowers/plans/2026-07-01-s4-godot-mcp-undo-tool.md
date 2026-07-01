# S4 — godot-mcp `undo` Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent a `godot_undo` core MCP tool that pops the live editor's undo history N steps, so the fluid executor's reversibility ledger can actually roll back arbitrary mutating tool calls.

**Architecture:** A GDScript `cmd_undo` handler in the addon calls the editor's `EditorUndoRedoManager` to undo the current scene history N times, returning how many actions were undone; a thin `godot_undo` core FastMCP tool forwards to it via the standard `route()` helper. This is the S4 subsystem of the fluid-agent epic (see `../../../godot-agents/docs/superpowers/specs/2026-07-01-fluid-agent-epic-design.md`).

**Tech Stack:** GDScript (Godot 4.7, `@tool` EditorPlugin), Python 3.11 + FastMCP, `pytest`.

**Repo:** this is a **godot-mcp** change (not godot-agents). Branch from `main`: `feat/s4-undo-tool`.

**Naming note:** the spec called it `godot_core_undo`, but core/meta tools drop the toolset prefix (naming rule #224), so the wire name is **`godot_undo`** and the addon command is **`cmd_undo`**.

---

## File structure

- **Modify** `godot/addons/godot_mcp/command_router.gd` — register `_handlers["cmd_undo"]` and add `func _cmd_undo(params)` (returning via the file's `_ok(...)` / `_fail(...)` helpers).
- **Create** `mcp_server/tools/undo.py` — `register_undo(mcp, bridge)` exposing the `godot_undo` core tool. New small module, mirrors `tools/health.py` (same `@mcp.tool(meta=..., tags={CORE_TAG})` shape).
- **Modify** `mcp_server/server.py` — call `register_undo(mcp, bridge)` inside `create_server`, alongside `register_health(...)` (~line 126). **Not** `main.py` — `main.py` only calls `create_server`; all `register_*` calls live in `create_server`.
- **Create** `tests/contract/test_undo.py` — contract tests using the **real** fake harness: `FakeAddonConnection(responder=...)` + `connector_for` + `Bridge` + `create_server` + `Client(server)`, asserting via `result.structured_content` and `conn.last_command()` (see `tests/contract/test_inspection.py` for the exact pattern).
- **Add** a live-editor `run_commands` smoke (in `tests/contract/test_undo.py` or `tests/contract/test_undo_smoke.py`): mutate → `cmd_undo` → assert reverted. Skipped when no live editor, consistent with existing live smokes.

---

## Task 1: Spike — confirm the exact undo API in a live editor

`EditorInterface.get_editor_undo_redo()` is already used and proven in this file (`command_router.gd:307`), so the *accessor* is not in doubt. What is uncertain in 4.7 is the **undo-trigger path**: whether `EditorUndoRedoManager` exposes `undo()`/`has_undo()` directly or requires `get_history_undo_redo(id).undo()`, whether `get_object_history_id(...)` exists, and *which* history id holds the agent's scene edits. Confirm those specifics empirically before writing the handler — do **not** guess.

- [ ] **Step 1: Drive a probe through `run_commands` in a live editor.** With the addon connected, send a `run_commands` batch that (a) creates a node, then (b) runs this probe and returns the observations:

```gdscript
var m := EditorInterface.get_editor_undo_redo()
var root := EditorInterface.get_edited_scene_root()
var out := {
    "has_direct_undo": m.has_method("undo"),               # does EditorUndoRedoManager expose undo() itself?
    "has_get_object_history_id": m.has_method("get_object_history_id"),
    "has_get_history_undo_redo": m.has_method("get_history_undo_redo"),
}
if m.has_method("get_object_history_id") and m.has_method("get_history_undo_redo"):
    var hid: int = m.get_object_history_id(root) if root != null else 0
    var ur := m.get_history_undo_redo(hid)                 # -> UndoRedo
    out["history_id"] = hid
    out["ur_is_null"] = ur == null
    out["ur_has_undo"] = ur != null and ur.has_undo()
    out["ur_action_name"] = (ur.get_current_action_name() if ur != null else "")
return out
```

Check `has_method` first so the probe never crashes on a renamed API; the returned booleans tell you which undo-trigger form to use in Task 2.

- [ ] **Step 2: Record the verified call.** Write the confirmed snippet into this plan (below Task 2) as the canonical undo call: either `m.undo()` (if `has_direct_undo` and it targets the scene history) **or** `m.get_history_undo_redo(m.get_object_history_id(root)).undo()`. Note the exact history-id source for a scene with and without an edited root (fall back to `EditorUndoRedoManager.GLOBAL_HISTORY` when `root == null`).

- [ ] **Step 3: Commit the spike finding.**

```bash
git add docs/superpowers/plans/2026-07-01-s4-godot-mcp-undo-tool.md
git commit -m "docs(s4): record verified editor undo API from live-editor spike"
```

> Everything below assumes the `get_history_undo_redo(...).undo()` form (the safe, well-documented path). If Step 1 shows a correct direct `m.undo()`, simplify the handler accordingly — the tests do not change.

---

## Task 2: GDScript `cmd_undo` handler

**Files:** Modify `godot/addons/godot_mcp/command_router.gd`

- [ ] **Step 1: Register the handler.** In the `_handlers[...]` registration block (near `_handlers["cmd_ping"]`), add:

```gdscript
	_handlers["cmd_undo"] = _cmd_undo
```

- [ ] **Step 2: Implement `_cmd_undo`.** Add near the other `_cmd_*` handlers. Handlers in this file return through the `_ok(result: Dictionary)` / `_fail(code, hint)` helpers (verified: `_cmd_get_project_info` returns `_ok({...})` at `command_router.gd:238`; `_ok`/`_fail` defined at ~`:494`/`:498`). Use the undo-trigger form confirmed by Task 1 — the snippet below assumes `get_history_undo_redo(...).undo()`:

```gdscript
func _cmd_undo(params: Dictionary) -> Dictionary:
	var count: int = int(params.get("count", 1))
	if count < 1:
		return _fail("INVALID_PARAM", "count must be >= 1")
	var dry_run: bool = bool(params.get("dry_run", false))
	var manager := EditorInterface.get_editor_undo_redo()
	var root := EditorInterface.get_edited_scene_root()
	var history_id: int = manager.get_object_history_id(root) if root != null else EditorUndoRedoManager.GLOBAL_HISTORY
	var ur := manager.get_history_undo_redo(history_id)
	var has_undo := ur != null and ur.has_undo()
	var next_action := ur.get_current_action_name() if has_undo else ""
	if dry_run:
		# Preview only — the editor UndoRedo API can't report stack depth without
		# popping, so a dry-run reports whether an undo is available and the next
		# action's name, and performs nothing.
		return _ok({"dry_run": true, "requested": count, "has_undo": has_undo, "would_undo_next": next_action})
	var undone := 0
	var last_action := ""
	while undone < count:
		if ur == null or not ur.has_undo():
			break
		last_action = ur.get_current_action_name()
		ur.undo()
		undone += 1
	return _ok({"undone": undone, "requested": count, "last_action": last_action, "dry_run": false})
```

(`cmd_undo` succeeds with `undone == 0` on an empty history rather than failing — an empty-history undo is a no-op, not an error; the caller decides. The Python tool turns `undone == 0` into a structured signal — Task 3. Replace `get_object_history_id`/`get_history_undo_redo`/`GLOBAL_HISTORY` with whatever Task 1 confirmed if they differ.)

- [ ] **Step 3: Track the addon change.** No test runs here yet (GDScript is exercised by the Task 5 smoke). Commit:

```bash
git add godot/addons/godot_mcp/command_router.gd
git commit -m "feat(addon): cmd_undo handler pops the scene undo history N steps"
```

---

## Task 3: Python `godot_undo` core tool (TDD)

**Files:** Create `mcp_server/tools/undo.py`; Test `tests/contract/test_undo.py`

- [ ] **Step 1: Write the failing contract test.** Use the **real** harness (copy the shape of `tests/contract/test_inspection.py`): a `_responder(cmd) -> ResponseEnvelope | None` keyed on `cmd.command`, a `FakeAddonConnection(responder=...)`, `connector_for`, `Bridge`, `create_server`, and `Client(server)`; assert payload via `result.structured_content` and the sent command via `conn.last_command()`.

```python
# tests/contract/test_undo.py
from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _undo_responder(undone: int):
    def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_undo":
            return ResponseEnvelope.success(
                cmd.id,
                {"undone": undone, "requested": cmd.params.get("count", 1), "last_action": "Create Node"},
            )
        return None  # bootstrap commands (cmd_ping/cmd_get_project_info) auto-answered by the fake
    return _responder


def _build(conn: FakeAddonConnection) -> FastMCP:
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge)


async def test_godot_undo_forwards_cmd_undo_with_count() -> None:
    conn = FakeAddonConnection(responder=_undo_responder(undone=2))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {"count": 2})
    assert conn.last_command().command == "cmd_undo"
    assert conn.last_command().params == {"count": 2, "dry_run": False}
    assert result.structured_content["undone"] == 2
    assert result.structured_content["nothing_to_undo"] is False


async def test_godot_undo_dry_run_previews_without_undoing() -> None:
    def _preview(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_undo":
            return ResponseEnvelope.success(
                cmd.id,
                {"dry_run": True, "requested": 1, "has_undo": True, "would_undo_next": "Create Node"},
            )
        return None

    conn = FakeAddonConnection(responder=_preview)
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {"dry_run": True})
    assert conn.last_command().params == {"count": 1, "dry_run": True}
    assert result.structured_content["would_undo_next"] == "Create Node"
    assert "nothing_to_undo" not in result.structured_content  # not added on a dry-run


async def test_godot_undo_reports_nothing_to_undo() -> None:
    conn = FakeAddonConnection(responder=_undo_responder(undone=0))
    async with Client(_build(conn)) as client:
        result = await client.call_tool("godot_undo", {})
    assert result.structured_content["undone"] == 0
    assert result.structured_content["nothing_to_undo"] is True
```

> Returning `None` from `_responder` for a non-`cmd_undo` command lets the fake's built-in bootstrap answer `cmd_ping`/`cmd_get_project_info` (see `FakeAddonConnection.send`), so the responder only handles what the test cares about.

- [ ] **Step 2: Run it, verify it fails.**

Run: `uv run pytest tests/contract/test_undo.py -q`
Expected: FAIL (`godot_undo` not registered / module missing).

- [ ] **Step 3: Implement the tool.** Mirror `tools/health.py` — a core tool carries `tags={CORE_TAG}` so the #224 naming lands it as `godot_undo` and the gating model keeps it always-on (a tag-less tool would be mis-gated).

```python
# mcp_server/tools/undo.py
"""Core `godot_undo` tool: pop the editor undo history N steps (S4)."""
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.safety import MUTATING
from mcp_server.tools._route import route


def register_undo(mcp: FastMCP, bridge: Bridge) -> None:
    @mcp.tool(meta=MUTATING, tags={CORE_TAG})
    async def godot_undo(count: int = 1, dry_run: bool = False) -> dict[str, Any]:
        """Undo the last ``count`` editor actions on the current scene's history.

        With ``dry_run=True``, previews (``has_undo`` + ``would_undo_next``) without
        undoing. Otherwise returns ``{undone, requested, last_action,
        nothing_to_undo}``. Undoing an empty history is a no-op (``undone == 0``,
        ``nothing_to_undo == True``), not an error — the reversibility ledger decides
        what that means.
        """
        if count < 1:
            raise ToolError("count must be >= 1")  # structured, pre-bridge (see Task 4)
        result = await route(bridge, "cmd_undo", {"count": count, "dry_run": dry_run})
        if not dry_run:
            result["nothing_to_undo"] = result.get("undone", 0) == 0
        return result
```

- [ ] **Step 4: Register it.** In `mcp_server/server.py`, inside `create_server`, add `from mcp_server.tools.undo import register_undo` (with the other tool imports) and `register_undo(mcp, bridge)` next to `register_health(mcp, bridge, config)`.

- [ ] **Step 5: Run the test, verify it passes.**

Run: `uv run pytest tests/contract/test_undo.py -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add mcp_server/tools/undo.py mcp_server/server.py tests/contract/test_undo.py
git commit -m "feat(server): godot_undo core tool forwarding to cmd_undo"
```

---

## Task 4: `count >= 1` guard (test the tool-body precondition)

The guard is already in the tool body (Task 3, Step 3: `if count < 1: raise ToolError(...)`) — a `ToolError` raised **before** the bridge round-trip. This task just pins it with a test. (Chosen over extending the `_route.py` `_preflight_validate` registry, whose validators are keyed by command name and shaped for path-containment — a tool-body guard is simpler and equally pre-bridge.)

- [ ] **Step 1: Failing test** — `godot_undo(count=0)` raises `ToolError` and never reaches the bridge. Add to `tests/contract/test_undo.py`:

```python
from fastmcp.exceptions import ToolError

async def test_godot_undo_rejects_nonpositive_count() -> None:
    conn = FakeAddonConnection(responder=_undo_responder(undone=0))
    with pytest.raises(ToolError, match="count"):
        async with Client(_build(conn)) as client:
            await client.call_tool("godot_undo", {"count": 0})
    # cmd_undo was never sent (only bootstrap commands, if any, reached the fake)
    assert all(
        CommandEnvelope.model_validate_json(m).command != "cmd_undo" for m in conn.sent
    )
```

- [ ] **Step 2:** Run → confirm PASS (the guard already exists from Task 3). If it fails, the guard is missing — add `if count < 1: raise ToolError("count must be >= 1")` at the top of `godot_undo`.
- [ ] **Step 3: Commit.**

```bash
git add tests/contract/test_undo.py && git commit -m "test(server): godot_undo rejects count < 1 pre-bridge"
```

---

## Task 5: Live-editor smoke (mutate → undo → assert reverted)

**Files:** add to `tests/contract/test_run_commands.py` pattern, or `tests/contract/test_undo_smoke.py`. Follows the existing skip-without-editor convention.

- [ ] **Step 1:** Write a smoke that, against a connected editor, sends a `run_commands` batch: `create_node` a uniquely-named child → assert it exists in the scene tree → `cmd_undo` → assert the node is gone and `undone == 1`. Guard/skip exactly as the existing live smokes do (no live bridge → skip, not fail).
- [ ] **Step 2:** Run the suite locally with an editor connected; confirm PASS. Without an editor, confirm it SKIPS (not fails).
- [ ] **Step 3: Commit.**

```bash
git add -A && git commit -m "test(s4): live smoke — create_node then cmd_undo reverts it"
```

---

## Task 6: Preflight + PR

- [ ] **Step 1:** Full preflight per repo rules: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `./.claude/hooks/check-no-skipped-tests.sh`.
- [ ] **Step 2:** Update `docs/tool-contracts.md` — add `godot_undo` to the core tool surface (safety class `mutating`, `count` param, returns `{undone, requested, last_action, nothing_to_undo}`).
- [ ] **Step 3:** Open the PR (`closes` the S4 tracking issue once filed). Wait for Qodo review, address comments, merge.

---

## Notes / risks

- **History fidelity (from the spec):** `cmd_undo` targets the *current scene* history; it assumes the agent is the sole mutator (true in eval/headless). A human editing the same scene concurrently could make undo pop *their* action — out of scope for v1, but the returned `last_action` lets the caller sanity-check what was undone before trusting the rollback.
- **Non-undo-tracked mutations** (file writes: `create_resource`, project settings, new script files) are **not** covered by `cmd_undo` — those use the ledger's `file_restore` strategy (S2), not this tool. `godot_undo` only reverses `editor_undo`-strategy actions.
- **`undone < requested`** is a legitimate outcome (history shorter than asked); the tool reports both so S2's ledger replay can detect a partial rollback and escalate.
