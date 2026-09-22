@tool
extends SceneTree
## Headless behavior test for the editor-history commands (issue #529).
##
## Run via: godot --headless --path godot/ --script res://tests/history_smoke.gd
## Exercises cmd_redo + cmd_list_history against a real UndoRedo object, with
## the EditorInterface-dependent history resolution overridden via the router's
## test seam (headless -s exposes EditorInterface but editor APIs are
## unavailable). Verifies: redo parity with undo's envelope, the dry-run
## preview shape, name resolution via get_action_name, and the orientation
## view's fields. Prints HISTORY_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()
	var ur := UndoRedo.new()
	var probe := RefCounted.new()
	probe.set("x", 0.0)

	# Override the shared history-resolution prologue: headless -s cannot drive
	# EditorUndoRedoManager (no editor). The seam is test-only; production
	# resolves the scene's own history.
	router.set_history_seam(ur)

	# Empty history: zero-values, not errors.
	var empty: Dictionary = router.handle({"id": "1", "command": "cmd_list_history", "params": {}})
	_eq(failures, "empty.ok", empty.get("ok"), true)
	var er: Dictionary = empty.get("result", {})
	_eq(failures, "empty.has_undo", er.get("has_undo"), false)
	_eq(failures, "empty.has_redo", er.get("has_redo"), false)
	_eq(failures, "empty.depth", er.get("depth"), 0)
	_eq(failures, "empty.recent", er.get("recent"), [])

	# Commit three actions, then undo two — the redo stack now holds two.
	_commit(ur, "Action A", probe, "set_x", 1.0)
	_commit(ur, "Action B", probe, "set_x", 2.0)
	_commit(ur, "Action C", probe, "set_x", 3.0)
	ur.undo()
	ur.undo()

	var mid: Dictionary = router.handle({"id": "2", "command": "cmd_list_history", "params": {}})
	var mr: Dictionary = mid.get("result", {})
	_eq(failures, "mid.has_undo", mr.get("has_undo"), true)
	_eq(failures, "mid.has_redo", mr.get("has_redo"), true)
	_eq(failures, "mid.depth", mr.get("depth"), 3)
	# 4.7 semantics: the current action is the last COMMITTED (undone-pointer)
	# action — after two undos that is Action A's entry. Redo re-applies the
	# action AFTER it (Action B).
	_eq(failures, "mid.current", mr.get("current_action"), "Action A")
	# A change-detector, not a stack depth: 4.7's version bumps on the FIRST
	# commit (from 0→2), then once per commit/redo; undo does not bump it.
	_eq(failures, "mid.version", mr.get("version"), 2)
	var recent: Array = mr.get("recent", [])
	if recent.size() == 3:
		_eq(failures, "mid.recent0", recent[0], "Action A")
		_eq(failures, "mid.recent2", recent[2], "Action C")
	else:
		failures.append("mid.recent: expected 3 entries, got %d" % recent.size())

	# Dry-run redo previews without applying: would_redo_next names Action B
	# (the action after the current pointer), and the pointer did not move.
	var preview: Dictionary = router.handle({
		"id": "3", "command": "cmd_redo",
		"params": {"count": 1, "dry_run": true},
	})
	var pr: Dictionary = preview.get("result", {})
	_eq(failures, "preview.ok", preview.get("ok"), true)
	_eq(failures, "preview.has_redo", pr.get("has_redo"), true)
	_eq(failures, "preview.next", pr.get("would_redo_next"), "Action B")
	_eq(failures, "preview.no_side_effect", ur.get_current_action_name(), "Action A")

	# Real redo: two steps forward (B then C), the pointer lands on Action C.
	var redone: Dictionary = router.handle({"id": "4", "command": "cmd_redo", "params": {"count": 2}})
	var rr: Dictionary = redone.get("result", {})
	_eq(failures, "redo.ok", redone.get("ok"), true)
	_eq(failures, "redo.redone", rr.get("redone"), 2)
	_eq(failures, "redo.requested", rr.get("requested"), 2)
	_eq(failures, "redo.last", rr.get("last_action"), "Action C")
	_eq(failures, "redo.dry_run", rr.get("dry_run"), false)
	_eq(failures, "redo.state", ur.get_current_action_name(), "Action C")

	# Redo past the top: honest no-op, nothing_to_redo implied by redone == 0.
	var exhausted: Dictionary = router.handle({"id": "5", "command": "cmd_redo", "params": {"count": 1}})
	_eq(failures, "exhausted.redone", exhausted.get("result", {}).get("redone"), 0)
	_eq(failures, "exhausted.ok", exhausted.get("ok"), true)

	# Undo parity after redo: the pointer walked back to the top cleanly.
	var undone: Dictionary = router.handle({"id": "6", "command": "cmd_undo", "params": {"count": 1}})
	_eq(failures, "undo.still_works", undone.get("result", {}).get("undone"), 1)
	_eq(failures, "undo.last", undone.get("result", {}).get("last_action"), "Action C")

	# count < 1 is a structured VALIDATION_ERROR, pre-side-effect.
	var bad: Dictionary = router.handle({"id": "7", "command": "cmd_redo", "params": {"count": 0}})
	_eq(failures, "bad.ok", bad.get("ok"), false)
	_eq(failures, "bad.error", bad.get("error"), "VALIDATION_ERROR")

	# The seam exists on the router (registration drift guard) and both
	# commands are registered for the server's handshake surface.
	_eq(failures, "registered_redo", router.has_command("cmd_redo"), true)
	_eq(failures, "registered_history", router.has_command("cmd_list_history"), true)

	if failures.is_empty():
		print("HISTORY_TEST_OK")
		quit(0)
	else:
		push_error("HISTORY_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


## Commit one named undo action: do sets a property on the probe object, undo
## restores the previous value. A plain RefCounted's scriptless `get` of an
## unset property returns null, so the probe's `x` is pre-seeded.
func _commit(history: UndoRedo, action: String, probe: Object, prop: String, value: float) -> void:
	var previous: Variant = probe.get(prop)
	history.create_action(action)
	history.add_do_property(probe, prop, value)
	history.add_undo_property(probe, prop, previous)
	history.commit_action()


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])