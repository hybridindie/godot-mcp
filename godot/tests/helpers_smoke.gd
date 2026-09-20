@tool
extends SceneTree
## Headless behavior test for the router refactor (issue #522): the shared
## helpers module + data-driven registration.
##
## Run via: godot --headless --path godot/ --script res://tests/helpers_smoke.gd
## Pins: HANDLERS registers every domain handler through one loop (all cmd_*
## names present); the helpers module owns the shared logic and stays
## router-agnostic (envelope builders passed as callables); the threshold
## decision lives there; the router keeps only envelope builders + dispatch.
## Prints HELPERS_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	# Data-driven registration: every handler registered (ping + a spot check
	# from several domains across the table).
	var expected := [
		"cmd_ping", "cmd_create_node", "cmd_write_script", "cmd_play_scene",
		"cmd_batch_set_property", "cmd_get_animation", "cmd_get_project_info",
	]
	for command in expected:
		if not router.has_command(command):
			failures.append("data-driven registration missing %s" % command)
	# 30 domains registered (31 HANDLERS entries include the table itself).
	if router._handlers.size() < 120:
		failures.append("suspiciously few commands registered: %d" % router._handlers.size())
	if router._instances.size() != Router.HANDLERS.size():
		failures.append("instances/table mismatch: %d vs %d" % [router._instances.size(), Router.HANDLERS.size()])

	# The helpers module owns the shared logic (no router-privates reach-in).
	var helpers := router._helpers
	if helpers == null:
		failures.append("_helpers must be created in _init")
	else:
		# Threshold decision + hint live there (#523), router delegates:
		_expect(failures, "undoable_20", helpers.undoable_for_count(20), true)
		_expect(failures, "undoable_21", helpers.undoable_for_count(21), false)
		if not helpers.undo_threshold_hint(25).contains("20-node UndoRedo threshold"):
			failures.append("helpers hint missing threshold wording")
		_expect(failures, "router_delegates_undoable", router._undoable_for_count(20), true)
		# Input validation + bitmask math (pure logic, no editor).
		_expect(failures, "valid_mouse", helpers.valid_mouse_button("left"), true)
		_expect(failures, "valid_mouse_bad", helpers.valid_mouse_button("nope"), false)
		_expect(failures, "valid_bits", helpers.valid_bits([1, 32]), true)
		_expect(failures, "valid_bits_bad", helpers.valid_bits([0, 33]), false)
		_expect(failures, "bitmask", helpers.bitmask([1, 3]), 5)
		# Input-event validation ("" = valid).
		_expect(failures, "input_event_ok", helpers.invalid_input_event({"type": "key", "key": "A"}), "")
		_expect(failures, "input_event_bad", helpers.invalid_input_event({"type": "nope"}), "'type' must be key/mouse/action")
		# resolve_node: headless -s restricts EditorInterface (get_edited_scene_root
		# unavailable), so the live editor path is covered by inspect_smoke +
		# the e2e suite; here pin the router-bound delegate wiring instead.
		_expect(failures, "router_has_resolve", router.has_command("cmd_node_exists"), true)
		# Persistence-truth helpers on editor-free inputs (PR #546 review: the
		# moved #458/#477 logic needs direct regression coverage — the live
		# editor paths are covered by test_persistence_e2e, these pin the
		# helpers' own pure branches):
		# with_persistence stamps the verdict onto a result (ok → persisted: true).
		var stamped: Dictionary = helpers.with_persistence({"path": "A"}, {"ok": true})
		_expect(failures, "with_persistence_ok", stamped.get("persisted"), true)
		if stamped.has("reason") or stamped.has("hint"):
			failures.append("with_persistence leaked reason/hint on ok verdict")
		# A failing verdict stamps persisted: false + reason + hint.
		var stamped_bad: Dictionary = helpers.with_persistence(
			{"path": "A"},
			{"ok": false, "reason": "node_not_owned", "hint": "not saved"},
		)
		_expect(failures, "with_persistence_bad", stamped_bad.get("persisted"), false)
		_expect(failures, "with_persistence_reason", stamped_bad.get("reason"), "node_not_owned")
		_expect(failures, "with_persistence_hint", stamped_bad.get("hint"), "not saved")
		# persistent_target(null) refuses with the honest no-scene verdict.
		var target: Dictionary = helpers.persistent_target(null)
		_expect(failures, "persistent_target_null", target.get("reason"), "node_not_owned")
		if not str(target.get("hint", "")).contains("No scene"):
			failures.append("persistent_target hint should name the no-scene case")
		# commit_add_child_with_persistence probes the verdict BEFORE the add
		# (#477 parent rule) — with a null parent the verdict is the no-scene
		# refusal. (The add itself needs a live editor; its full path is
		# covered by the create-family e2e tests.)

	# Envelope builders stay on the router.
	var body: Dictionary = router._ok({"x": 1})
	_expect(failures, "ok", body.get("ok"), true)
	var bad: Dictionary = router._fail("VALIDATION_ERROR", "h", "f")
	_expect(failures, "fail.error", bad.get("error"), "VALIDATION_ERROR")
	_expect(failures, "fail.required", bad.get("required"), "f")

	router.dispose()
	# dispose is trivial but complete: the table is empty, dispatch refuses.
	if not router._handlers.is_empty():
		failures.append("dispose did not clear _handlers")
	var after: Dictionary = router.handle({"id": "9", "command": "cmd_ping", "params": {}})
	_expect(failures, "post_dispose", after.get("error"), "VALIDATION_ERROR")

	router = null

	if failures.is_empty():
		print("HELPERS_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("HELPERS_TEST_FAIL")
		quit(1)


func _expect(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])