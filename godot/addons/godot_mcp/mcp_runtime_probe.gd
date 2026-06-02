extends Node
## godot-mcp runtime probe (issue #66). Runs **in the game**, not the editor.
##
## Add this script as an autoload in the *consuming* game's project to enable godot-mcp
## live runtime inspection/input while the game runs from the editor. It registers an
## EngineDebugger message capture on the "godot_mcp" channel and answers queries from the
## addon's MCPDebugger (editor side). It does nothing outside a debug session, so it is
## safe to leave enabled (it no-ops in exported/non-debug builds).

const MAX_DEPTH := 32


func _ready() -> void:
	if EngineDebugger.is_active():
		EngineDebugger.register_message_capture("godot_mcp", _capture)
		EngineDebugger.send_message("godot_mcp:ready", [])


## Capture handler: the "godot_mcp:" prefix is stripped before this is called.
func _capture(message: String, data: Array) -> bool:
	match message:
		"ping":
			EngineDebugger.send_message("godot_mcp:pong", [])
			return true
		"get_scene_tree":
			EngineDebugger.send_message("godot_mcp:scene_tree", [_serialize_tree()])
			return true
		"simulate_key":
			_inject_key(_payload(data))
			return true
		"simulate_mouse":
			_inject_mouse(_payload(data))
			return true
		"simulate_action":
			_inject_action(_payload(data))
			return true
		"play_input_sequence":
			_play_input_sequence(_payload(data))
			return true
	return false


# --- input simulation (issue #36) ------------------------------------------

const _MOUSE_BUTTONS := {
	"left": MOUSE_BUTTON_LEFT,
	"right": MOUSE_BUTTON_RIGHT,
	"middle": MOUSE_BUTTON_MIDDLE,
	"wheel_up": MOUSE_BUTTON_WHEEL_UP,
	"wheel_down": MOUSE_BUTTON_WHEEL_DOWN,
}


func _payload(data: Array) -> Dictionary:
	return data[0] if not data.is_empty() and data[0] is Dictionary else {}


func _inject_key(d: Dictionary) -> void:
	var event := InputEventKey.new()
	event.keycode = OS.find_keycode_from_string(str(d.get("key", "")))
	event.pressed = bool(d.get("pressed", true))
	event.shift_pressed = bool(d.get("shift", false))
	event.ctrl_pressed = bool(d.get("ctrl", false))
	event.alt_pressed = bool(d.get("alt", false))
	event.meta_pressed = bool(d.get("meta", false))
	Input.parse_input_event(event)
	_ack()


func _inject_mouse(d: Dictionary) -> void:
	var position := Vector2(float(d.get("x", 0.0)), float(d.get("y", 0.0)))
	var button_name := str(d.get("button", ""))
	if button_name.is_empty():
		var motion := InputEventMouseMotion.new()
		motion.position = position
		motion.relative = Vector2(float(d.get("relative_x", 0.0)), float(d.get("relative_y", 0.0)))
		Input.parse_input_event(motion)
	else:
		if not _MOUSE_BUTTONS.has(button_name):
			return  # ignore an unknown button name rather than defaulting to a left click
		var event := InputEventMouseButton.new()
		event.button_index = _MOUSE_BUTTONS[button_name]
		event.pressed = bool(d.get("pressed", true))
		event.position = position
		Input.parse_input_event(event)
	_ack()


func _inject_action(d: Dictionary) -> void:
	var action := StringName(str(d.get("action", "")))
	if not InputMap.has_action(action):
		return  # action not in the running game's InputMap — drop it (no ack)
	if bool(d.get("pressed", true)):
		Input.action_press(action, float(d.get("strength", 1.0)))
	else:
		Input.action_release(action)
	_ack()


## Replay a sequence of events with a delay between each (runs as a coroutine).
func _play_input_sequence(d: Dictionary) -> void:
	var events: Array = d.get("events", [])
	var delay_ms := int(d.get("delay_ms", 0))
	for event in events:
		if not (event is Dictionary):
			continue
		match str(event.get("type", "")):
			"key":
				_inject_key(event)
			"mouse":
				_inject_mouse(event)
			"action":
				_inject_action(event)
		if delay_ms > 0:
			await get_tree().create_timer(float(delay_ms) / 1000.0).timeout


## Tell the editor an input event was injected, so it can confirm delivery.
func _ack() -> void:
	EngineDebugger.send_message("godot_mcp:input_ack", [])


func _serialize_tree() -> Dictionary:
	return _node_to_dict(get_tree().root, 0)


## JSON-safe { name, type, path, children } snapshot of the live node, bounded by depth.
func _node_to_dict(node: Node, depth: int) -> Dictionary:
	var children: Array = []
	if depth < MAX_DEPTH:
		for child in node.get_children():
			children.append(_node_to_dict(child, depth + 1))
	return {
		"name": String(node.name),
		"type": node.get_class(),
		"path": String(node.get_path()),
		"children": children,
	}
