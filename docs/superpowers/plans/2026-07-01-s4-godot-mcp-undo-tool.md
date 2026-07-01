# S4 — godot-mcp `undo` Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent a `godot_undo` core MCP tool that pops the live editor's undo history N steps, so the fluid executor's reversibility ledger can actually roll back arbitrary mutating tool calls.

**Architecture:** A GDScript `cmd_undo` handler in the addon calls the editor's `EditorUndoRedoManager` to undo the current scene history N times, returning how many actions were undone; a thin `godot_undo` core FastMCP tool forwards to it via the standard `route()` helper. This is the S4 subsystem of the fluid-agent epic (see `../../../godot-agents/docs/superpowers/specs/2026-07-01-fluid-agent-epic-design.md`).

**Tech Stack:** GDScript (Godot 4.7, `@tool` EditorPlugin), Python 3.11 + FastMCP, `pytest`.

**Repo:** this is a **godot-mcp** change (not godot-agents). Branch from `main`: `feat/s4-undo-tool`.

**Naming note:** the spec called it `godot_core_undo`, but core/meta tools drop the toolset prefix (naming rule #224), so the wire name is **`godot_undo`** and the addon command is **`cmd_undo`**.

---

## File structure

- **Modify** `godot/addons/godot_mcp/command_router.gd` — register `_handlers["cmd_undo"]` and add `func _cmd_undo(params)`.
- **Create** `mcp_server/tools/undo.py` — `register_undo(mcp, bridge)` exposing the `godot_undo` core tool. (New small module, mirrors `tools/health.py`; keeps the core surface focused.)
- **Modify** `mcp_server/main.py` — call `register_undo(...)` alongside the other core registrations.
- **Create** `tests/contract/test_undo.py` — contract tests for the tool (forwarding + error surface) using the bridge fake.
- **Modify** `tests/contract/test_run_commands.py` (or add `tests/contract/test_undo_smoke.py`) — a live-editor `run_commands` smoke: mutate → `cmd_undo` → assert reverted. Marked/skipped when no live editor, consistent with existing smoke handling.

---

## Task 1: Spike — confirm the exact undo API in a live editor

The 4.7 `EditorUndoRedoManager` surface is ambiguous from docs alone (it may expose `undo()`/`has_undo()` directly, or require `get_history_undo_redo(id).undo()`), and *which* history id holds the agent's scene edits must be confirmed. Resolve this empirically before writing the handler — do **not** guess.

- [ ] **Step 1: Drive a probe through `run_commands` in a live editor.** With the addon connected, send a `run_commands` batch that (a) creates a node, then (b) runs this probe and returns the observations:

```gdscript
var m := EditorInterface.get_editor_undo_redo()
var root := EditorInterface.get_edited_scene_root()
var hid := m.get_object_history_id(root)          # confirm this method exists + returns the scene history
var ur := m.get_history_undo_redo(hid)            # -> UndoRedo
return {
    "has_direct_undo": m.has_method("undo"),       # does EditorUndoRedoManager expose undo() itself?
    "history_id": hid,
    "ur_is_null": ur == null,
    "ur_has_undo": ur != null and ur.has_undo(),
    "ur_action_name": (ur.get_current_action_name() if ur != null else ""),
}
```

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

- [ ] **Step 2: Implement `_cmd_undo`.** Add near the other `_cmd_*` handlers. Match the **return shape of existing handlers in this file** (return the plain result `Dictionary`; the router wraps it into the `{id, ok, result, error}` envelope — verify against `_cmd_get_project_info`):

```gdscript
func _cmd_undo(params: Dictionary) -> Dictionary:
	var count: int = int(params.get("count", 1))
	if count < 1:
		return {"error": "INVALID_PARAM", "hint": "count must be >= 1"}
	var manager := EditorInterface.get_editor_undo_redo()
	var root := EditorInterface.get_edited_scene_root()
	var history_id: int = manager.get_object_history_id(root) if root != null else EditorUndoRedoManager.GLOBAL_HISTORY
	var ur := manager.get_history_undo_redo(history_id)
	var undone := 0
	var last_action := ""
	while undone < count:
		if ur == null or not ur.has_undo():
			break
		last_action = ur.get_current_action_name()
		ur.undo()
		undone += 1
	return {"undone": undone, "requested": count, "last_action": last_action}
```

(`cmd_undo` reports `undone` rather than erroring on an empty history — an empty-history undo is a no-op, not a failure; the caller decides. The Python tool converts `undone == 0` into a structured signal — Task 3.)

- [ ] **Step 3: Track the addon change.** No test runs here yet (GDScript is exercised by the Task 5 smoke). Commit:

```bash
git add godot/addons/godot_mcp/command_router.gd
git commit -m "feat(addon): cmd_undo handler pops the scene undo history N steps"
```

---

## Task 3: Python `godot_undo` core tool (TDD)

**Files:** Create `mcp_server/tools/undo.py`; Test `tests/contract/test_undo.py`

- [ ] **Step 1: Write the failing contract test.** Mirror an existing contract test's fake-bridge setup (see `tests/contract/test_run_commands.py` for the fake wiring and `tests/fakes.py`).

```python
# tests/contract/test_undo.py
import pytest
from tests.fakes import FakeBridge, build_test_server  # match the helpers used by test_run_commands.py

@pytest.mark.asyncio
async def test_godot_undo_forwards_cmd_undo_with_count():
    bridge = FakeBridge(result={"undone": 2, "requested": 2, "last_action": "Create Node"})
    server = build_test_server(bridge)  # registers core tools incl. register_undo
    result = await server.call_tool("godot_undo", {"count": 2})
    assert bridge.last_command == "cmd_undo"
    assert bridge.last_params == {"count": 2}
    assert result["undone"] == 2

@pytest.mark.asyncio
async def test_godot_undo_reports_nothing_to_undo():
    bridge = FakeBridge(result={"undone": 0, "requested": 1, "last_action": ""})
    server = build_test_server(bridge)
    result = await server.call_tool("godot_undo", {})
    assert result["undone"] == 0
    assert result["nothing_to_undo"] is True
```

> Adjust the imports/harness calls to match whatever `tests/contract/test_run_commands.py` actually uses — reuse that file's exact pattern rather than inventing helpers.

- [ ] **Step 2: Run it, verify it fails.**

Run: `uv run pytest tests/contract/test_undo.py -q`
Expected: FAIL (`godot_undo` not registered / module missing).

- [ ] **Step 3: Implement the tool.**

```python
# mcp_server/tools/undo.py
"""Core `godot_undo` tool: pop the editor undo history N steps (#S4)."""
from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.bridge import Bridge
from mcp_server.safety import MUTATING
from mcp_server.tools._route import route


def register_undo(mcp: FastMCP, bridge: Bridge) -> None:
    @mcp.tool(meta=MUTATING)  # core tool: no toolset tag -> always-on
    async def godot_undo(count: int = 1) -> dict:
        """Undo the last ``count`` editor actions on the current scene's history.

        Returns ``{undone, requested, last_action, nothing_to_undo}``. Undoing an
        empty history is a no-op (``undone == 0``, ``nothing_to_undo == True``), not
        an error — the reversibility ledger decides what that means.
        """
        result = await route(bridge, "cmd_undo", {"count": count})
        result["nothing_to_undo"] = result.get("undone", 0) == 0
        return result
```

- [ ] **Step 4: Register it.** In `mcp_server/main.py`, alongside the other core registrations, add `from mcp_server.tools.undo import register_undo` and `register_undo(mcp, bridge)`.

- [ ] **Step 5: Run the test, verify it passes.**

Run: `uv run pytest tests/contract/test_undo.py -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add mcp_server/tools/undo.py mcp_server/main.py tests/contract/test_undo.py
git commit -m "feat(server): godot_undo core tool forwarding to cmd_undo"
```

---

## Task 4: Preflight validation for `cmd_undo`

**Files:** wherever command param validation lives (find via `grep -rn "cmd_run_commands" mcp_server/` — the preflight validator `_preflight_validate` in `_route.py` or a validation registry).

- [ ] **Step 1: Failing test** — `godot_undo(count=0)` raises a structured `ToolError` ("count must be >= 1"), not a bridge round-trip.

```python
@pytest.mark.asyncio
async def test_godot_undo_rejects_nonpositive_count():
    bridge = FakeBridge(result={})
    server = build_test_server(bridge)
    with pytest.raises(Exception) as exc:  # ToolError
        await server.call_tool("godot_undo", {"count": 0})
    assert "count" in str(exc.value)
    assert bridge.last_command is None  # never reached the bridge
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Add a `count >= 1` precondition for `cmd_undo` following the existing validation pattern (the GDScript handler already guards, but preflight keeps it a structured `ToolError` and avoids the round-trip).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "feat(server): preflight-validate godot_undo count >= 1"
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
