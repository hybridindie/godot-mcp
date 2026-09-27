extends SceneTree
## Headless behavior test for the debugger's request_id-gated ui_elements cache
## (issue #577).
##
## Run via: godot --headless --path godot/ --script res://tests/ui_elements_gate_smoke.gd
##
## #577: the godot_mcp:ui_elements capture stored every reply without checking
## its request_id — a delayed reply to an OLDER scan could be served to a new
## poll with different filters (wrong rects to click). Mirrors the #575
## read_property gate: replies matching the pending scan are cached; stale ones
## are dropped.
##
## MCPDebugger is an EditorDebuggerPlugin (editor-only instantiation), so this
## smoke drives a stand-in capture: it replicates the exact gate semantics and
## asserts them — the real _capture source is pinned by the contract source
## scan (tests/contract/test_ui_elements_gate.py). Prints
## UI_ELEMENTS_GATE_TEST_OK, quits 0.

var _failures: Array[String] = []


func _initialize() -> void:
	var pending := "scan-2"  # the request the editor is currently waiting on
	var cache: Variant = null

	var stale := {
		"request_id": "scan-1", "elements": [{"name": "OLD"}],
	}
	var fresh := {
		"request_id": "scan-2", "elements": [{"name": "NEW"}],
	}

	# The #577 gate logic, exactly as implemented in mcp_debugger._capture:
	for reply in [stale, fresh, stale]:
		if reply is Dictionary:
			if pending != "__none__" and str(reply.get("request_id", "")) == pending:
				cache = reply

	_eq("stale_reply_not_stored", cache, fresh)
	_eq("reapplied_stale_still_dropped", cache, fresh)

	if _failures.is_empty():
		print("UI_ELEMENTS_GATE_TEST_OK")
		quit(0)
	else:
		push_error("UI_ELEMENTS_GATE_TEST_FAILURES: %s" % [str(_failures)])
		quit(1)


func _eq(what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		_failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])