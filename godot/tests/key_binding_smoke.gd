extends SceneTree
## Headless behavior test for the runtime probe's key injection vs physical
## keycode bindings (issue #570).
##
## Run via: godot --headless --path godot/ --script res://tests/key_binding_smoke.gd
##
## Godot 4's Input Map editor binds actions by PHYSICAL keycode by default, and
## an InputEventKey carrying only `keycode` never matches such a binding (docs:
## InputEventKey comparison is keycode → physical_keycode, first match wins;
## real hardware events populate both). The probe's _inject_key set only
## `keycode`, so simulated keys were silently ignored by actions bound to
## physical keys — the binding type the editor produces by default (#570).
##
## Adds the real probe script to the tree, binds one action by keycode and one
## by physical keycode, dispatches `simulate_key` through the probe's real
## capture handler, and asserts BOTH actions fire like they would for a real
## keypress. Prints KEY_BINDING_TEST_OK, quits 0.

const TEST_KEY_ACTION := &"mcp_test_key_action"
const TEST_PHYSICAL_ACTION := &"mcp_test_physical_action"
const Probe := preload("res://addons/godot_mcp/mcp_runtime_probe.gd")

var _frame := 0


func _initialize() -> void:
	# Bind one action by keycode (legacy/authoring style) and one by physical
	# keycode (the Input Map editor's default when you press a key).
	if not InputMap.has_action(TEST_KEY_ACTION):
		InputMap.add_action(TEST_KEY_ACTION)
	var code_bind := InputEventKey.new()
	code_bind.keycode = KEY_E
	InputMap.action_add_event(TEST_KEY_ACTION, code_bind)

	if not InputMap.has_action(TEST_PHYSICAL_ACTION):
		InputMap.add_action(TEST_PHYSICAL_ACTION)
	var phys_bind := InputEventKey.new()
	phys_bind.physical_keycode = KEY_E
	InputMap.action_add_event(TEST_PHYSICAL_ACTION, phys_bind)

	var probe := Node.new()
	probe.name = "MCPRuntimeProbe"
	probe.set_script(Probe)
	root.add_child(probe)


func _process(_delta: float) -> bool:
	_frame += 1
	if _frame == 1:
		# Dispatch through the probe's real handler path (the same route a
		# cmd_simulate_key message takes) — engine-level check, no bridge.
		var probe := root.get_node("MCPRuntimeProbe")
		probe._capture("simulate_key", [{"key": "E", "pressed": true}])
		return false
	if _frame < 3:
		return false  # let the input system flush the queued event

	var failures: Array[String] = []
	_eq(failures, "keycode-bound action fires", Input.is_action_pressed(TEST_KEY_ACTION), true)
	_eq(
		failures,
		"physical-keycode-bound action fires",
		Input.is_action_pressed(TEST_PHYSICAL_ACTION),
		true,
	)
	# The engine-level match both bindings rely on (issue #570's repro table).
	var captured := InputEventKey.new()
	captured.keycode = KEY_E
	captured.physical_keycode = KEY_E
	_eq(failures, "both-keycodes event matches physical binding", captured.is_action(TEST_PHYSICAL_ACTION), true)

	if failures.is_empty():
		print("KEY_BINDING_TEST_OK")
		quit(0)
	else:
		push_error("KEY_BINDING_TEST_FAILURES: %s" % [str(failures)])
		quit(1)
	return false


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])