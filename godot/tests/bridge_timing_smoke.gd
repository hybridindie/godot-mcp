@tool
extends SceneTree
## Headless behavior test for the bridge's command-timing + outcome reporting
## (issue #520, outcome args #589).
##
## Run via: godot --headless --path godot/ --script res://tests/bridge_timing_smoke.gd
## Pins the #520 fix: no dead timing state (_pending_times removed), and the
## `command_completed` signal reports ONE honest number — handler execution
## time (exec_ms) — with no mislabeled "latency" third arg. #589: the signal
## also carries the response verdict (ok: bool, error_code: String) so the
## dock can log outcomes, not just dispatch. Drives `_handle_text()` directly
## (no networking): a valid ping envelope and a malformed one must each emit
## exactly one command_completed with exec_ms > 0 — ok=true for the ping,
## ok=false with the VALIDATION_ERROR code for the malformed one.
## Prints BRIDGE_TIMING_TEST_OK, quits 0 on success.

const Bridge := preload("res://addons/godot_mcp/mcp_bridge.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var bridge := Bridge.new()

	# The dead state must be gone (#520): the bridge carries no per-command
	# pending-time dictionary it never populates.
	if "pending_times" in bridge or "_pending_times" in bridge:
		failures.append("bridge still carries the never-populated _pending_times state")

	# One command_completed per handled envelope, exec_ms honest (> 0),
	# plus the response verdict (#589).
	var completions: Array[Dictionary] = []
	bridge.command_completed.connect(
		func(command: String, exec_ms: float, ok: bool, error_code: String) -> void:
			completions.append({"command": command, "exec_ms": exec_ms, "ok": ok, "error": error_code})
	)

	bridge._handle_text(JSON.stringify({"id": "1", "command": "cmd_ping", "params": {}}))
	if completions.size() != 1:
		failures.append("expected one command_completed for the ping, got %d" % completions.size())
	elif completions[0]["command"] != "cmd_ping":
		failures.append("completed command name: expected 'cmd_ping', got '%s'" % completions[0]["command"])
	elif completions[0]["exec_ms"] <= 0.0:
		failures.append("exec_ms should be > 0 (handler time), got %f" % completions[0]["exec_ms"])
	elif completions[0]["ok"] != true:
		failures.append("ping should report ok=true, got %s" % str(completions[0]["ok"]))
	elif completions[0]["error"] != "":
		failures.append("ping should carry an empty error code, got '%s'" % completions[0]["error"])

	completions.clear()
	bridge._handle_text("not json")
	if completions.size() != 1:
		failures.append("malformed envelope: expected one command_completed, got %d" % completions.size())
	elif completions[0]["command"] != "?":
		failures.append("malformed envelope should report command '?', got '%s'" % completions[0]["command"])
	elif completions[0]["ok"] != false:
		failures.append("malformed envelope should report ok=false, got %s" % str(completions[0]["ok"]))
	elif completions[0]["error"] != "VALIDATION_ERROR":
		failures.append("malformed envelope should carry the VALIDATION_ERROR code, got '%s'" % completions[0]["error"])

	# A dispatched-but-failing command (unknown verb) reports the router's
	# structured error code, not a success.
	completions.clear()
	bridge._handle_text(JSON.stringify({"id": "2", "command": "cmd_no_such_verb", "params": {}}))
	if completions.size() != 1:
		failures.append("unknown command: expected one command_completed, got %d" % completions.size())
	elif completions[0]["ok"] != false:
		failures.append("unknown command should report ok=false, got %s" % str(completions[0]["ok"]))
	elif completions[0]["error"] != "VALIDATION_ERROR":
		failures.append("unknown command should carry VALIDATION_ERROR, got '%s'" % completions[0]["error"])

	bridge.dispose()
	bridge = null

	if failures.is_empty():
		print("BRIDGE_TIMING_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("BRIDGE_TIMING_TEST_FAIL")
		quit(1)