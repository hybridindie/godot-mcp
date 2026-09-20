@tool
extends SceneTree
## Headless behavior test for the shared UndoRedo batch threshold (issue #523).
##
## Run via: godot --headless --path godot/ --script res://tests/threshold_smoke.gd
## Exercises the router's threshold decision + hint helpers — the one site all
## three batch tools (batch_set_property, batch_create_nodes, apply_node_edits)
## consume — across the boundary: 19 (undoable), 20 (exactly at, undoable),
## 21 (one over, non-undoable + hint), 500 (well over). No editor needed: the
## helpers are pure given a count. Prints THRESHOLD_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	# Boundary: 19 and 20 stay undoable; 21 and above bypass undo.
	_expect(failures, "n19", router._undoable_for_count(19), true)
	_expect(failures, "n20", router._undoable_for_count(20), true)
	_expect(failures, "n21", router._undoable_for_count(21), false)
	_expect(failures, "n500", router._undoable_for_count(500), false)

	# The hint names the count and the shared threshold value, and is honest
	# about undo coverage (the #461 wording contract).
	var hint := router._undo_threshold_hint(25)
	if not hint.contains("25"):
		failures.append("hint.count: should name the batch size: %s" % hint)
	if not hint.contains("20-node UndoRedo threshold"):
		failures.append("hint.threshold: should name the 20-node threshold: %s" % hint)
	if not hint.contains("Undo will not revert"):
		failures.append("hint.honesty: should say undo will not revert: %s" % hint)
	# The composite applies variant uses the "applies" noun.
	var applies_hint := router._undo_threshold_hint(25, "applies")
	if not applies_hint.contains("25 applies"):
		failures.append("hint.noun: applies variant should name applies: %s" % applies_hint)

	# The const is declared once (the decision and the hint both derive from it).
	if Router.MCP_UNDO_THRESHOLD != 20:
		failures.append("const: expected 20, got %d" % Router.MCP_UNDO_THRESHOLD)

	router = null

	if failures.is_empty():
		print("THRESHOLD_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("THRESHOLD_TEST_FAIL")
		quit(1)


func _expect(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])