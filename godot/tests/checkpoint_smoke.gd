extends SceneTree
## Headless: cmd_undo_state reports the current action/count for checkpoints (#760).

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _init() -> void:
	var failures: Array = []
	var router: Variant = Router.new()
	var ur := UndoRedo.new()
	router.set_history_seam(ur)

	var empty: Dictionary = router.handle({"id": "1", "command": "cmd_undo_state", "params": {}})
	_eq(failures, "empty.available", empty.get("result", {}).get("available"), true)
	_eq(failures, "empty.current", empty.get("result", {}).get("current"), -1)

	for name in ["a", "b"]:
		ur.create_action(name)
		ur.add_do_method(func() -> void: pass)
		ur.commit_action()

	var state: Dictionary = router.handle({"id": "2", "command": "cmd_undo_state", "params": {}})
	_eq(failures, "state.current", state.get("result", {}).get("current"), 1)
	_eq(failures, "state.count", state.get("result", {}).get("count"), 2)

	ur.undo()
	var undone: Dictionary = router.handle({"id": "3", "command": "cmd_undo_state", "params": {}})
	_eq(failures, "undone.current", undone.get("result", {}).get("current"), 0)
	_eq(failures, "undone.count", undone.get("result", {}).get("count"), 2)

	if failures.is_empty():
		print("CHECKPOINT_TEST_OK")
	else:
		push_error("CHECKPOINT_TEST_FAILURES: %s" % JSON.stringify(failures))
	quit()


func _eq(failures: Array, label: String, actual: Variant, expected: Variant) -> void:
	if actual != expected:
		failures.append("%s: expected %s, got %s" % [label, str(expected), str(actual)])
