@tool
extends SceneTree
## Headless behavior test for the cmd_run_commands batch meta-command (issue #167).
##
## Run via: godot --headless --path godot/ --script res://tests/run_commands_smoke.gd
## Exercises the router's batch dispatch without EditorInterface: editor-free
## sub-commands (cmd_ping) run in order; a nested run_commands is rejected (no
## recursion/crash); and a malformed entry yields a structured per-command error
## that still carries a "command" field (so the server's SubCommandResult validates).

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	# A batch of editor-free sub-commands runs in one call, in order.
	var ok_batch: Dictionary = router.handle({
		"id": "1",
		"command": "cmd_run_commands",
		"params": {"commands": [
			{"command": "cmd_ping", "params": {}},
			{"command": "cmd_ping", "params": {}},
		]},
	})
	var r: Dictionary = ok_batch.get("result", {})
	_eq(failures, "batch.ok", ok_batch.get("ok"), true)
	_eq(failures, "batch.ok_all", r.get("ok_all"), true)
	_eq(failures, "batch.count", r.get("count"), 2)
	var results: Array = r.get("results", [])
	if results.size() == 2:
		_eq(failures, "batch.cmd0", results[0].get("command"), "cmd_ping")
		_eq(failures, "batch.sub_ok", results[0].get("ok"), true)
	else:
		failures.append("batch results size wrong: %d" % results.size())

	# Nesting is rejected per-command — no recursion into _cmd_run_commands.
	var nested: Dictionary = router.handle({
		"id": "2",
		"command": "cmd_run_commands",
		"params": {"commands": [
			{"command": "cmd_run_commands", "params": {"commands": []}},
		], "stop_on_error": false},
	})
	var nr: Array = nested.get("result", {}).get("results", [])
	_eq(failures, "nested.ok_all", nested.get("result", {}).get("ok_all"), false)
	if nr.size() == 1:
		_eq(failures, "nested.err", nr[0].get("error"), "VALIDATION_ERROR")
		_eq(failures, "nested.cmd", nr[0].get("command"), "cmd_run_commands")
	else:
		failures.append("nested results size wrong: %d" % nr.size())

	# A non-dict entry yields a structured per-command error carrying "command".
	var bad: Dictionary = router.handle({
		"id": "3",
		"command": "cmd_run_commands",
		"params": {"commands": ["not-a-dict"], "stop_on_error": false},
	})
	var br: Array = bad.get("result", {}).get("results", [])
	if br.size() == 1:
		_eq(failures, "bad.err", br[0].get("error"), "VALIDATION_ERROR")
		_eq(failures, "bad.has_command", br[0].has("command"), true)
	else:
		failures.append("bad results size wrong: %d" % br.size())

	if failures.is_empty():
		print("RUN_COMMANDS_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("RUN_COMMANDS_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
