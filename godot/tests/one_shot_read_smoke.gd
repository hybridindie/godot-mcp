extends SceneTree
## Headless behavior test for the probe's dedicated one-shot property read (issue #571).
##
## Run via: godot --headless --path godot/ --script res://tests/one_shot_read_smoke.gd
##
## #571: the runtime probe has a single monitor slot; a one-shot read implemented
## as monitor_property(samples=1) silently REPLACED a running capture, and
## get_property_samples then reported the wrong series as ready. The dedicated
## read_property message reads the value now and shares no state with the monitor.
##
## Adds the real probe script to the tree, starts a monitor capture, dispatches
## read_property through the probe's real capture handler mid-capture, and asserts:
## the one-shot value arrives, the monitor slot is untouched, and error paths
## (unknown node / unknown property) are structured. Prints ONE_SHOT_READ_TEST_OK.

const Probe := preload("res://addons/godot_mcp/mcp_runtime_probe.gd")

var _probe: Node
var _frame := 0


func _initialize() -> void:
	var holder := Node2D.new()
	holder.name = "Holder"
	root.add_child(holder)
	var target := Node2D.new()
	target.name = "Body"
	target.position = Vector2(10, 20)
	holder.add_child(target)

	_probe = Node.new()
	_probe.name = "MCPRuntimeProbe"
	_probe.set_script(Probe)
	root.add_child(_probe)


func _process(_delta: float) -> bool:
	_frame += 1
	match _frame:
		1:
			# Start a monitor capture (5 frames) — the thing a one-shot must not clobber.
			_probe._capture("monitor_property", [{
				"node_path": "/root/Holder/Body", "property": "position",
				"samples": 5, "on_change_only": false,
			}])
			# Same frame: the one-shot read for a DIFFERENT node/property.
			_probe._capture("read_property", [{
				"node_path": "/root/Holder/Body", "property": "rotation", "request_id": "r1",
			}])
			return false
		2:
			# The monitor capture is still running (frames remaining)…
			_eq("monitor_still_running", _probe._monitor_remaining > 0, true)
			# …and the one-shot reply is already available via the debugger channel
			# (sent synchronously — but EngineDebugger is inactive headless, so call
			# the reader directly for the value check).
			var reply: Dictionary = _probe._read_property({
				"node_path": "/root/Holder/Body", "property": "rotation", "request_id": "r2",
			})
			_eq("read_ready", reply.get("ready"), true)
			_eq("read_error_empty", reply.get("error"), "")
			_eq("read_value", reply.get("value"), 0.0)
			_eq("read_request_id", reply.get("request_id"), "r2")
			# Error paths are structured, not crashes:
			var bad_node: Dictionary = _probe._read_property({
				"node_path": "/root/Nope", "property": "position", "request_id": "r3",
			})
			_eq("bad_node_error", str(bad_node.get("error")).contains("node not found"), true)
			var bad_prop: Dictionary = _probe._read_property({
				"node_path": "/root/Holder/Body", "property": "no_such_prop", "request_id": "r4",
			})
			_eq("bad_prop_error", str(bad_prop.get("error")).contains("no property"), true)
			return false
		6:
			# The capture survived the one-shot: it completes on its own schedule
			# (5 monitor frames started at frame 1 — the one-shot shares no state)
			# and holds position samples — NOT the one-shot's single rotation value.
			_eq("capture_completed", _probe._monitor_remaining, 0)
			_eq("capture_target_property", _probe._monitor_property, "position")
			var values: Array = []
			for sample in _probe._monitor_samples:
				values.append((sample as Dictionary).get("value"))
			_eq("capture_series_is_position_dicts", values.size() > 0, true)
			if not values.is_empty():
				_eq(
					"capture_series_shape",
					(values[0] as Dictionary).has("x") and (values[0] as Dictionary).has("y"),
					true,
				)
			if _failures.is_empty():
				print("ONE_SHOT_READ_TEST_OK")
				quit(0)
			else:
				push_error("ONE_SHOT_READ_TEST_FAILURES: %s" % [str(_failures)])
				quit(1)
	return false


var _failures: Array[String] = []


func _eq(what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		_failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


func _process_probe(_delta: float) -> void:
	pass