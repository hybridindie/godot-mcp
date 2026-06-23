@tool
extends SceneTree
## Headless behavior test for MCPInputActionRead (issue #219 P2).
##
## Run via: godot --headless --path godot/ --script res://tests/input_action_read_smoke.gd
## Builds real InputEvent objects (no ProjectSettings) and verifies the pure event
## serialization round-trips into the add_input_event shape against the live Godot API.

const InputActionRead := preload("res://addons/godot_mcp/input_action_read.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	# A Ctrl+Space key event, a left mouse button, and a joypad motion.
	var key := InputEventKey.new()
	key.keycode = OS.find_keycode_from_string("Space")
	key.ctrl_pressed = true
	var mouse := InputEventMouseButton.new()
	mouse.button_index = MOUSE_BUTTON_LEFT
	var motion := InputEventJoypadMotion.new()
	motion.device = 0
	motion.axis = JOY_AXIS_LEFT_X
	motion.axis_value = 1.0

	var data: Dictionary = InputActionRead.serialize("jump", 0.25, [key, mouse, motion])
	_eq(failures, "action", data.get("action"), "jump")
	_eq(failures, "deadzone", data.get("deadzone"), 0.25)

	var events: Array = data["events"]
	if events.size() != 3:
		failures.append("expected 3 events, got %s" % str(events))
	else:
		var k: Dictionary = events[0]
		_eq(failures, "key.event_type", k.get("event_type"), "key")
		# keycode round-trips through OS.find_keycode_from_string (the writer's inverse).
		_eq(failures, "key.keycode", OS.find_keycode_from_string(k.get("keycode", "")), key.keycode)
		_eq(failures, "key.ctrl", k.get("ctrl"), true)
		_eq(failures, "key.shift", k.get("shift"), false)
		_eq(failures, "mouse.button", events[1].get("button"), "left")
		_eq(failures, "motion.event_type", events[2].get("event_type"), "joypad_motion")
		_eq(failures, "motion.axis_value", events[2].get("axis_value"), 1.0)

	# Output must be JSON-safe.
	if JSON.stringify(data) == "":
		failures.append("serialized events are not JSON-safe")

	if failures.is_empty():
		print("INPUT_ACTION_READ_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("INPUT_ACTION_READ_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
