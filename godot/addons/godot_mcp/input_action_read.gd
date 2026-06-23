@tool
class_name MCPInputActionRead
extends RefCounted
## Pure serialization of input-action events (issue #219 P2 — rollback enabler). Takes
## the events Array + deadzone from a ProjectSettings input/<action> entry (no
## ProjectSettings / EditorInterface access here), so verifiable headlessly (see
## godot/tests/input_action_read_smoke.gd). Each event is emitted in the same shape
## add_input_event accepts, so remove_input_action / clear_input_action_events are
## invertible.

const _MOUSE_BUTTON_NAMES := {
	MOUSE_BUTTON_LEFT: "left",
	MOUSE_BUTTON_RIGHT: "right",
	MOUSE_BUTTON_MIDDLE: "middle",
	MOUSE_BUTTON_WHEEL_UP: "wheel_up",
	MOUSE_BUTTON_WHEEL_DOWN: "wheel_down",
}


## { action, deadzone, events:[{event_type, ...kind-specific keys}] }.
static func serialize(action: String, deadzone: float, events: Array) -> Dictionary:
	var out: Array = []
	for ev in events:
		var d := _serialize_event(ev)
		if not d.is_empty():
			out.append(d)
	return {"action": action, "deadzone": deadzone, "events": out}


## One InputEvent → an add_input_event-shaped dict (empty for unsupported types).
static func _serialize_event(ev: Variant) -> Dictionary:
	if ev is InputEventKey:
		var d := {
			"event_type": "key",
			"shift": ev.shift_pressed,
			"ctrl": ev.ctrl_pressed,
			"alt": ev.alt_pressed,
			"meta": ev.meta_pressed,
		}
		# Mirror the writer, which sets keycode OR physical_keycode; OS.get_keycode_string
		# is the inverse of the writer's OS.find_keycode_from_string.
		if ev.keycode != 0:
			d["keycode"] = OS.get_keycode_string(ev.keycode)
		if ev.physical_keycode != 0:
			d["physical_keycode"] = OS.get_keycode_string(ev.physical_keycode)
		return d
	elif ev is InputEventMouseButton:
		return {
			"event_type": "mouse",
			"button": _MOUSE_BUTTON_NAMES.get(ev.button_index, str(ev.button_index)),
		}
	elif ev is InputEventJoypadButton:
		return {"event_type": "joypad_button", "device": ev.device, "joy_button_index": ev.button_index}
	elif ev is InputEventJoypadMotion:
		return {
			"event_type": "joypad_motion",
			"device": ev.device,
			"axis": ev.axis,
			"axis_value": ev.axis_value,
		}
	return {}
