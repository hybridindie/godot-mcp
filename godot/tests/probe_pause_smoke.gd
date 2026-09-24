extends SceneTree
## Headless behavior test for the runtime probe's pause behavior (issue #565).
##
## Run via: godot --headless --path godot/ --script res://tests/probe_pause_smoke.gd
## Adds the real probe script to the tree, pauses the SceneTree (what a game's
## pause menu / death screen does), and asserts the probe can still process:
## with the default INHERIT mode a paused tree starves the probe's _process —
## capture_frame / monitor_property / force_break all defer to it — into tool
## timeouts (#565). PROCESS_MODE_ALWAYS is the engine-documented fix.
## Prints PROBE_PAUSE_TEST_OK, quits 0.

const Probe := preload("res://addons/godot_mcp/mcp_runtime_probe.gd")

var _frame := 0


func _initialize() -> void:
	# Add the real probe script to the tree as an autoload-equivalent node; its
	# _ready() runs on add_child. (Nodes join the pause resolution only from the
	# first iteration onward, so assertions happen in _process below.)
	var probe := Node.new()
	probe.name = "MCPRuntimeProbe"
	probe.set_script(Probe)
	root.add_child(probe)

	# Pause the whole tree — exactly what a game's pause menu / death screen does.
	paused = true


func _process(_delta: float) -> bool:
	_frame += 1
	if _frame != 1:
		return false
	# can_process() is the engine's own pause decision (Node docs): INHERIT under
	# a paused tree returns false; PROCESS_MODE_ALWAYS returns true. Asserted
	# from the first iteration, where the pause decision is valid.
	var failures: Array[String] = []
	var probe := root.get_node("MCPRuntimeProbe")
	_eq(failures, "probe_can_process_while_paused", probe.can_process(), true)
	_eq(failures, "process_mode_always", probe.process_mode, Node.PROCESS_MODE_ALWAYS)
	# The frame-grab state machine still services a request end to end.
	probe._capture("capture_frame", [{"request_id": "pause-smoke"}])
	_eq(failures, "frame_pending_set", probe._frame_pending, true)
	probe._process(0.016)
	_eq(failures, "frame_grab_consumed", probe._frame_pending, false)

	if failures.is_empty():
		print("PROBE_PAUSE_TEST_OK")
		quit(0)
	else:
		push_error("PROBE_PAUSE_TEST_FAILURES: %s" % [str(failures)])
		quit(1)
	return false


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])