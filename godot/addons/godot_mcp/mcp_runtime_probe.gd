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
		"monitor_property":
			_start_monitor(_payload(data))
			return true
		"find_ui":
			EngineDebugger.send_message("godot_mcp:ui_elements", [_find_ui(_payload(data))])
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


# --- runtime inspection (issue #35) ----------------------------------------

const _MONITOR_MAX_SAMPLES := 300

var _monitor_target: NodePath = NodePath()
var _monitor_property := ""
var _monitor_remaining := 0
var _monitor_samples: Array = []
var _monitor_error := ""


## Sample the monitored property once per frame until the requested count is reached,
## then push the completed series to the editor (bounded capture — no perpetual stream).
func _process(_delta: float) -> void:
	if _monitor_remaining <= 0:
		return
	_monitor_remaining -= 1
	var node := get_node_or_null(_monitor_target)
	if node == null:
		_monitor_error = "node not found at '%s'" % String(_monitor_target)
		_monitor_remaining = 0
	else:
		_monitor_samples.append({
			"frame": Engine.get_process_frames(),
			"value": _json_safe(node.get(_monitor_property)),
		})
	if _monitor_remaining <= 0:
		_push_samples()


func _start_monitor(d: Dictionary) -> void:
	_monitor_target = NodePath(str(d.get("node_path", "")))
	_monitor_property = str(d.get("property", ""))
	_monitor_samples = []
	_monitor_error = ""
	var count := clampi(int(d.get("samples", 30)), 1, _MONITOR_MAX_SAMPLES)
	var node := get_node_or_null(_monitor_target)
	if node == null:
		_monitor_error = "node not found at '%s'" % String(_monitor_target)
		_monitor_remaining = 0
		_push_samples()
		return
	if not (_monitor_property in node):
		_monitor_error = "no property '%s' on the node" % _monitor_property
		_monitor_remaining = 0
		_push_samples()
		return
	_monitor_remaining = count  # _process collects one sample per frame


func _push_samples() -> void:
	EngineDebugger.send_message("godot_mcp:property_samples", [{
		"node_path": String(_monitor_target),
		"property": _monitor_property,
		"samples": _monitor_samples,
		"error": _monitor_error,
		"ready": true,
	}])


## Collect live Control nodes matching the filters, with their global rect (for clicking).
func _find_ui(d: Dictionary) -> Dictionary:
	var out: Array = []
	_collect_controls(
		get_tree().root,
		str(d.get("name_contains", "")).to_lower(),
		str(d.get("class_filter", "")),
		bool(d.get("visible_only", false)),
		out,
	)
	return {"request_id": str(d.get("request_id", "")), "elements": out}


func _collect_controls(
	node: Node, name_contains: String, class_filter: String, visible_only: bool, out: Array
) -> void:
	if node is Control:
		var matches := true
		if not name_contains.is_empty() and not String(node.name).to_lower().contains(name_contains):
			matches = false
		if matches and not class_filter.is_empty() and not node.is_class(class_filter):
			matches = false
		if matches and visible_only and not node.is_visible_in_tree():
			matches = false
		if matches:
			out.append(_ui_element(node))
	for child in node.get_children():
		_collect_controls(child, name_contains, class_filter, visible_only, out)


func _ui_element(control: Control) -> Dictionary:
	var rect := control.get_global_rect()
	var element := {
		"path": String(control.get_path()),
		"name": String(control.name),
		"node_class": control.get_class(),
		"visible": control.is_visible_in_tree(),
		"rect": {"x": rect.position.x, "y": rect.position.y, "w": rect.size.x, "h": rect.size.y},
	}
	if "text" in control:  # Button / Label / LineEdit / …
		element["text"] = str(control.text)
	return element


## Minimal JSON-safe conversion for monitored property values (common Godot types).
func _json_safe(value: Variant) -> Variant:
	match typeof(value):
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return {"x": value.x, "y": value.y, "z": value.z}
		TYPE_COLOR:
			return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
		TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			return value
		_:
			return str(value)
