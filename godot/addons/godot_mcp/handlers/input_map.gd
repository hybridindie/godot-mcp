@tool
class_name MCPInputMapHandlers
extends RefCounted
## Domain handler: input map.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const InputActionRead := preload("../input_action_read.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_input_action"] = _cmd_add_input_action
	handlers["cmd_add_input_event"] = _cmd_add_input_event
	handlers["cmd_clear_input_action_events"] = _cmd_clear_input_action_events
	handlers["cmd_remove_input_action"] = _cmd_remove_input_action
	handlers["cmd_get_input_action_events"] = _cmd_get_input_action_events


# -- handlers ----------------------------------------------------------------

## Read an input action's deadzone + events (issue #219 P2). The inverse of the
## input_map writers; delegates per-event serialization to MCPInputActionRead. Events
## come from ProjectSettings (project.godot), the same store the writers persist to.
func _cmd_get_input_action_events(params: Dictionary) -> Dictionary:
	var action_name := str(params.get("action", ""))
	if action_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "action is required.")
	var setting_key := "input/" + action_name
	if not ProjectSettings.has_setting(setting_key):
		return _router._fail("RESOURCE_NOT_FOUND", "No input action '%s'." % action_name)
	var action_data: Dictionary = ProjectSettings.get_setting(setting_key)
	var deadzone := float(action_data.get("deadzone", 0.5))
	var events: Array = action_data.get("events", [])
	return _router._ok(InputActionRead.serialize(action_name, deadzone, events))


func _cmd_add_input_action(params: Dictionary) -> Dictionary:
	var action_name := str(params.get("name", ""))
	if action_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "name is required.")
	var deadzone: float = float(params.get("deadzone", 0.5))
	var setting_key := "input/" + action_name
	if ProjectSettings.has_setting(setting_key):
		return _router._fail("VALIDATION_ERROR", "Action '%s' already exists." % action_name)
	var action_data: Dictionary = {"deadzone": deadzone, "events": []}
	_commit_action_change("Add input action %s" % action_name, action_name, null, action_data)
	return _router._ok({"name": action_name, "added": true, "deadzone": deadzone})



func _cmd_remove_input_action(params: Dictionary) -> Dictionary:
	var action_name := str(params.get("name", ""))
	if action_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "name is required.")
	if not params.get("confirm", false):
		return _router._fail("PRECONDITION_FAILED", "This call removes an action and all its events. Set confirm=True to proceed.", "confirm")
	var setting_key := "input/" + action_name
	if not ProjectSettings.has_setting(setting_key):
		return _router._fail("RESOURCE_NOT_FOUND", "No input action '%s'." % action_name)
	var old_data: Dictionary = _read_action(setting_key)
	_commit_action_change("Remove input action %s" % action_name, action_name, old_data, null)
	return _router._ok({"name": action_name, "removed": true})



func _cmd_add_input_event(params: Dictionary) -> Dictionary:
	var action_name := str(params.get("action", ""))
	if action_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "action is required.")
	var setting_key := "input/" + action_name
	if not ProjectSettings.has_setting(setting_key):
		return _router._fail("RESOURCE_NOT_FOUND", "No input action '%s'." % action_name)
	var old_data: Dictionary = _read_action(setting_key)
	var action_data: Dictionary = old_data.duplicate(true)
	var events: Array = action_data.get("events", [])
	var event_type := str(params.get("event_type", ""))
	var ev: InputEvent = null
	match event_type:
		"key":
			ev = InputEventKey.new()
			var code_str := str(params.get("keycode", ""))
			var phys_str := str(params.get("physical_keycode", ""))
			if not code_str.is_empty():
				ev.keycode = OS.find_keycode_from_string(code_str)
			elif not phys_str.is_empty():
				ev.physical_keycode = OS.find_keycode_from_string(phys_str)
			else:
				return _router._fail("VALIDATION_ERROR", "Set 'keycode' or 'physical_keycode' for key events.")
			if bool(params.get("shift", false)):
				ev.shift_pressed = true
			if bool(params.get("ctrl", false)):
				ev.ctrl_pressed = true
			if bool(params.get("alt", false)):
				ev.alt_pressed = true
			if bool(params.get("meta", false)):
				ev.meta_pressed = true
		"mouse":
			ev = InputEventMouseButton.new()
			var btn := str(params.get("button", ""))
			match btn:
				"left":
					ev.button_index = MOUSE_BUTTON_LEFT
				"right":
					ev.button_index = MOUSE_BUTTON_RIGHT
				"middle":
					ev.button_index = MOUSE_BUTTON_MIDDLE
				"wheel_up":
					ev.button_index = MOUSE_BUTTON_WHEEL_UP
				"wheel_down":
					ev.button_index = MOUSE_BUTTON_WHEEL_DOWN
				_:
					return _router._fail("VALIDATION_ERROR", "Unknown mouse button '%s'." % btn)
		"joypad_button":
			ev = InputEventJoypadButton.new()
			ev.device = int(params.get("device", 0))
			ev.button_index = int(params.get("joy_button_index", 0))
		"joypad_motion":
			ev = InputEventJoypadMotion.new()
			ev.device = int(params.get("device", 0))
			ev.axis = int(params.get("axis", 0))
			ev.axis_value = float(params.get("axis_value", 1.0))
		_:
			return _router._fail("VALIDATION_ERROR", "Unknown event_type '%s'. Use key/mouse/joypad_button/joypad_motion." % event_type)
	if ev == null:
		return _router._fail("INTERNAL_ERROR", "Failed to build input event.")
	events.append(ev)
	action_data["events"] = events
	_commit_action_change("Add input event to %s" % action_name, action_name, old_data, action_data)
	return _router._ok({"action": action_name, "event_index": events.size() - 1, "added": true})



func _cmd_clear_input_action_events(params: Dictionary) -> Dictionary:
	var action_name := str(params.get("action", ""))
	if action_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "action is required.")
	if not params.get("confirm", false):
		return _router._fail("PRECONDITION_FAILED", "This call removes all events for '%s'. Set confirm=True to proceed." % action_name, "confirm")
	var setting_key := "input/" + action_name
	if not ProjectSettings.has_setting(setting_key):
		return _router._fail("RESOURCE_NOT_FOUND", "No input action '%s'." % action_name)
	var old_data: Dictionary = _read_action(setting_key)
	var action_data: Dictionary = old_data.duplicate(true)
	action_data["events"] = []
	_commit_action_change("Clear input events of %s" % action_name, action_name, old_data, action_data)
	return _router._ok({"action": action_name, "cleared": true})


# -- undo plumbing (issue #907) ------------------------------------------------

## A private copy of the stored action: ProjectSettings hands back the Dictionary
## it holds, so editing it in place would also rewrite the undo snapshot. The
## InputEvent objects are shared, which is fine — no writer mutates an event.
func _read_action(setting_key: String) -> Dictionary:
	var data: Dictionary = ProjectSettings.get_setting(setting_key)
	return data.duplicate(true)


## Register one undoable action that swaps the `input/<action>` setting between
## `old_value` and `new_value` (null erases the setting). Godot's own Input Map
## editor makes these edits undoable the same way. The scene-root context puts the
## action on the history godot_undo reads (#640); with no scene it stays global.
func _commit_action_change(label: String, action_name: String, old_value: Variant, new_value: Variant) -> void:
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action(label, UndoRedo.MERGE_DISABLE, _router.asset_action_context())
	ur.add_do_method(self, "_apply_action", action_name, new_value)
	ur.add_undo_method(self, "_apply_action", action_name, old_value)
	ur.commit_action()


## Both sides of every input-map action: write + persist the setting, then mirror
## it into the editor's runtime InputMap so the session stays consistent.
func _apply_action(action_name: String, value: Variant) -> void:
	ProjectSettings.set_setting("input/" + action_name, value)
	ProjectSettings.save()
	if value == null:
		if InputMap.has_action(action_name):
			InputMap.erase_action(action_name)
		return
	var data: Dictionary = value
	var events: Array = data.get("events", [])
	if not InputMap.has_action(action_name):
		# Match the pre-#907 behaviour: an event-less action is settings-only.
		if events.is_empty():
			return
		InputMap.add_action(action_name, float(data.get("deadzone", 0.5)))
	else:
		InputMap.action_erase_events(action_name)
		InputMap.action_set_deadzone(action_name, float(data.get("deadzone", 0.5)))
	for ev: Variant in events:
		if ev is InputEvent:
			InputMap.action_add_event(action_name, ev)
