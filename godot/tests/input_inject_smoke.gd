@tool
extends SceneTree
## Headless input-injection test (issue #201).
##
## Run via: godot --headless --path godot/ --script res://tests/input_inject_smoke.gd
##
## Verifies that the synthesized key + mouse-button events the runtime probe
## injects (mcp_runtime_probe.gd: InputEventKey/InputEventMouseButton +
## Input.parse_input_event) still reach `_input` and still update InputMap action
## state under Godot 4.7's device-ID change (GH-116274: real keyboard events now
## carry device 16 and mouse 32, where they were 0 — and 0 now means joypad).
##
## Prints INPUT_INJECT_TEST_OK on success, or INPUT_INJECT_TEST_FAIL: <reason>.

const TEST_ACTION := &"mcp_test_inject_action"

var _key_seen := false
var _mouse_seen := false
var _frames := 0


class Capture:
	extends Node
	var on_key: Callable
	var on_mouse: Callable

	func _input(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and on_key.is_valid():
			on_key.call(event)
		elif event is InputEventMouseButton and event.pressed and on_mouse.is_valid():
			on_mouse.call(event)


func _initialize() -> void:
	# Bind a test action to SPACE so we can also assert action-state routing.
	if not InputMap.has_action(TEST_ACTION):
		InputMap.add_action(TEST_ACTION)
	var bind := InputEventKey.new()
	bind.keycode = KEY_SPACE
	InputMap.action_add_event(TEST_ACTION, bind)

	var capture := Capture.new()
	capture.on_key = func(_e: InputEvent) -> void: _key_seen = true
	capture.on_mouse = func(_e: InputEvent) -> void: _mouse_seen = true
	root.add_child(capture)

	# Synthesize exactly as the runtime probe does (no explicit device set).
	var key := InputEventKey.new()
	key.keycode = KEY_SPACE
	key.pressed = true
	Input.parse_input_event(key)

	var mouse := InputEventMouseButton.new()
	mouse.button_index = MOUSE_BUTTON_LEFT
	mouse.pressed = true
	mouse.position = Vector2(10, 10)
	Input.parse_input_event(mouse)


func _process(_delta: float) -> bool:
	# Give the input system a couple of frames to flush the queued events.
	_frames += 1
	if _frames < 3:
		return false

	var failures: Array[String] = []
	if not _key_seen:
		failures.append("InputEventKey did not reach _input")
	if not _mouse_seen:
		failures.append("InputEventMouseButton did not reach _input")
	if not Input.is_action_pressed(TEST_ACTION):
		failures.append("synthesized key did not set InputMap action state")

	if failures.is_empty():
		print("INPUT_INJECT_TEST_OK")
	else:
		print("INPUT_INJECT_TEST_FAIL: " + ", ".join(failures))
	return true  # quit
