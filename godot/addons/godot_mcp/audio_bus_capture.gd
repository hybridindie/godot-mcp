@tool
class_name MCPAudioBusCapture
extends RefCounted
## Capture / restore an AudioServer bus for undoable removal (issue #219 G8). Operates on
## the live AudioServer (available headlessly) — no EditorInterface — so it is verifiable
## in a headless smoke (see godot/tests/audio_bus_capture_smoke.gd). The remove handler
## captures a bus before AudioServer.remove_bus and registers restore() as the UndoRedo
## undo step, so undo rebuilds the bus with all its properties and effects.


## Snapshot a bus's name/routing/flags and its full effect stack (effect objects + enabled
## flags). The effects are kept as live AudioEffect references, not serialized — this dict
## feeds restore(), it never crosses the bridge.
static func capture(index: int) -> Dictionary:
	var effects: Array = []
	for e in AudioServer.get_bus_effect_count(index):
		effects.append({
			"effect": AudioServer.get_bus_effect(index, e),
			"enabled": AudioServer.is_bus_effect_enabled(index, e),
		})
	return {
		"name": String(AudioServer.get_bus_name(index)),
		"volume_db": AudioServer.get_bus_volume_db(index),
		"send": String(AudioServer.get_bus_send(index)),
		"mute": AudioServer.is_bus_mute(index),
		"solo": AudioServer.is_bus_solo(index),
		"bypass": AudioServer.is_bus_bypassing_effects(index),
		"effects": effects,
	}


## Re-create a captured bus at ``index`` with its properties and effect stack.
static func restore(index: int, state: Dictionary) -> void:
	AudioServer.add_bus(index)
	AudioServer.set_bus_name(index, state["name"])
	AudioServer.set_bus_volume_db(index, state["volume_db"])
	AudioServer.set_bus_send(index, state["send"])
	AudioServer.set_bus_mute(index, state["mute"])
	AudioServer.set_bus_solo(index, state["solo"])
	AudioServer.set_bus_bypass_effects(index, state["bypass"])
	var effects: Array = state["effects"]
	for i in effects.size():
		AudioServer.add_bus_effect(index, effects[i]["effect"], i)
		AudioServer.set_bus_effect_enabled(index, i, effects[i]["enabled"])
