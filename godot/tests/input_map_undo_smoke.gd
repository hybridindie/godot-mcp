@tool
extends SceneTree
## Headless behavior test: input-map mutations are undoable (issue #907).
##
## Run via: godot --headless --editor --path godot/ --script res://tests/input_map_undo_smoke.gd
## `--editor` is required: only an editor process exposes EditorUndoRedoManager.
## Drives the four input-map writers through the real router, then undoes each
## on the editor's history and asserts ProjectSettings is back where it was.
## No scene is open, so the actions land on the global history. Prints
## INPUT_MAP_UNDO_TEST_OK and quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")
const ACTION := "mcp_input_map_undo_smoke"
const KEY := "input/" + ACTION


func _initialize() -> void:
	var failures: Array[String] = []
	_cleanup()
	var router := Router.new()

	# add_input_action → undo removes it.
	var added := _call(router, "cmd_add_input_action", {"name": ACTION, "deadzone": 0.3})
	_eq(failures, "add.ok", added.get("ok"), true)
	_eq(failures, "add.exists", ProjectSettings.has_setting(KEY), true)
	_eq(failures, "add.undo", _undo(), true)
	_eq(failures, "add.undone", ProjectSettings.has_setting(KEY), false)

	# Re-add for the event steps.
	_call(router, "cmd_add_input_action", {"name": ACTION, "deadzone": 0.3})

	# add_input_event → undo drops the event (settings + runtime InputMap).
	var ev := _call(router, "cmd_add_input_event", {"action": ACTION, "event_type": "key", "keycode": "Space"})
	_eq(failures, "event.ok", ev.get("ok"), true)
	_eq(failures, "event.count", _event_count(), 1)
	_eq(failures, "event.undo", _undo(), true)
	_eq(failures, "event.undone", _event_count(), 0)
	_eq(failures, "event.undone.input_map", _runtime_event_count(), 0)

	# Re-add the event for the clear/remove steps.
	_call(router, "cmd_add_input_event", {"action": ACTION, "event_type": "key", "keycode": "Space"})

	# clear_input_action_events → undo brings the event back.
	var cleared := _call(router, "cmd_clear_input_action_events", {"action": ACTION, "confirm": true})
	_eq(failures, "clear.ok", cleared.get("ok"), true)
	_eq(failures, "clear.count", _event_count(), 0)
	_eq(failures, "clear.undo", _undo(), true)
	_eq(failures, "clear.restored", _event_count(), 1)
	_eq(failures, "clear.restored.input_map", _runtime_event_count(), 1)

	# remove_input_action → undo brings the action, its deadzone and events back.
	var removed := _call(router, "cmd_remove_input_action", {"name": ACTION, "confirm": true})
	_eq(failures, "remove.ok", removed.get("ok"), true)
	_eq(failures, "remove.gone", ProjectSettings.has_setting(KEY), false)
	_eq(failures, "remove.undo", _undo(), true)
	_eq(failures, "remove.restored", ProjectSettings.has_setting(KEY), true)
	_eq(failures, "remove.restored.count", _event_count(), 1)
	if ProjectSettings.has_setting(KEY):
		var data: Dictionary = ProjectSettings.get_setting(KEY)
		_eq(failures, "remove.restored.deadzone", is_equal_approx(float(data.get("deadzone", 0.0)), 0.3), true)
		var events: Array = data.get("events", [])
		if events.size() == 1:
			_eq(failures, "remove.restored.event_is_key", events[0] is InputEventKey, true)

	# Undo payloads stay private (#921 review): the restored event is not the
	# object held in undo history, so editing the live setting can't rewrite it.
	if ProjectSettings.has_setting(KEY):
		var live: Dictionary = ProjectSettings.get_setting(KEY)
		var live_events: Array = live.get("events", [])
		if live_events.size() == 1 and live_events[0] is InputEventKey:
			(live_events[0] as InputEventKey).keycode = KEY_A
			_eq(failures, "alias.redo", _redo(), true)  # remove again
			_eq(failures, "alias.undo", _undo(), true)  # restore from history
			var restored: Dictionary = ProjectSettings.get_setting(KEY, {})
			var restored_events: Array = restored.get("events", [])
			var keycode := -1
			if restored_events.size() == 1 and restored_events[0] is InputEventKey:
				keycode = int((restored_events[0] as InputEventKey).keycode)
			_eq(failures, "alias.restored_keycode", keycode, int(KEY_SPACE))

	var ur := _global_history()
	if ur != null:
		ur.clear_history()
	_cleanup()

	if failures.is_empty():
		print("INPUT_MAP_UNDO_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("INPUT_MAP_UNDO_TEST_FAIL")
		quit(1)


func _call(router: MCPCommandRouter, command: String, params: Dictionary) -> Dictionary:
	return router.handle({"id": command, "command": command, "params": params})


## The manager creates a history lazily on its first action, so resolve it per
## call rather than once up front (null before anything was committed).
func _global_history() -> UndoRedo:
	return EditorInterface.get_editor_undo_redo().get_history_undo_redo(
		EditorUndoRedoManager.GLOBAL_HISTORY
	)


func _undo() -> bool:
	var ur := _global_history()
	return ur != null and ur.undo()


func _redo() -> bool:
	var ur := _global_history()
	return ur != null and ur.redo()


func _event_count() -> int:
	if not ProjectSettings.has_setting(KEY):
		return -1
	var data: Dictionary = ProjectSettings.get_setting(KEY)
	return (data.get("events", []) as Array).size()


func _runtime_event_count() -> int:
	if not InputMap.has_action(ACTION):
		return 0
	return InputMap.action_get_events(ACTION).size()


## Leave project.godot exactly as the checkout had it.
func _cleanup() -> void:
	if ProjectSettings.has_setting(KEY):
		ProjectSettings.set_setting(KEY, null)
		ProjectSettings.save()
	if InputMap.has_action(ACTION):
		InputMap.erase_action(ACTION)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	# Type first: comparing mismatched types is a script error in Godot 4 (#467).
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
