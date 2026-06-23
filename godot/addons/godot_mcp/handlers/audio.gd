@tool
class_name MCPAudioHandlers
extends RefCounted
## Domain handler: audio.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const AudioBusCapture := preload("res://addons/godot_mcp/audio_bus_capture.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_audio_bus"] = _cmd_add_audio_bus
	handlers["cmd_add_audio_bus_effect"] = _cmd_add_audio_bus_effect
	handlers["cmd_add_audio_player"] = _cmd_add_audio_player
	handlers["cmd_get_audio_bus_layout"] = _cmd_get_audio_bus_layout
	handlers["cmd_remove_audio_bus"] = _cmd_remove_audio_bus
	handlers["cmd_remove_audio_bus_effect"] = _cmd_remove_audio_bus_effect


# -- handlers ----------------------------------------------------------------

func _cmd_add_audio_player(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var player_type := str(params.get("player_type", "AudioStreamPlayer"))
	if player_type not in ["AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D"]:
		return _router._fail("VALIDATION_ERROR", "player_type must be an AudioStreamPlayer/2D/3D.")
	var player := ClassDB.instantiate(player_type) as Node
	if player == null:
		return _router._fail("VALIDATION_ERROR", "Could not instantiate '%s'." % player_type)
	player.name = str(params.get("name", player_type))
	var stream_path := str(params.get("stream_path", ""))
	if not stream_path.is_empty():
		if not ResourceLoader.exists(stream_path):
			return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % stream_path)
		var stream: Resource = ResourceLoader.load(stream_path)
		if not (stream is AudioStream):
			return _router._fail("VALIDATION_ERROR", "'%s' is not an AudioStream." % stream_path)
		player.set("stream", stream)
	_router._apply_props(player, params.get("properties", {}))
	var path := _router._commit_add_child(parent, player, "Add %s" % player.name)
	return _router._ok({"node_path": path, "player_type": player_type, "created": true})



func _cmd_get_audio_bus_layout(_params: Dictionary) -> Dictionary:
	var buses: Array = []
	for i in AudioServer.get_bus_count():
		var effects: Array = []
		for e in AudioServer.get_bus_effect_count(i):
			var effect := AudioServer.get_bus_effect(i, e)
			effects.append({
				"index": e,
				"type": effect.get_class() if effect != null else "",
				"enabled": AudioServer.is_bus_effect_enabled(i, e),
			})
		buses.append({
			"index": i,
			"name": String(AudioServer.get_bus_name(i)),
			"volume_db": AudioServer.get_bus_volume_db(i),
			"muted": AudioServer.is_bus_mute(i),
			"solo": AudioServer.is_bus_solo(i),
			"bypass": AudioServer.is_bus_bypassing_effects(i),
			"effects": effects,
		})
	return _router._ok({"buses": buses})



func _cmd_add_audio_bus(params: Dictionary) -> Dictionary:
	var bus_name := str(params.get("name", ""))
	if bus_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	if AudioServer.get_bus_index(bus_name) != -1:
		return _router._fail("VALIDATION_ERROR", "An audio bus named '%s' already exists." % bus_name)
	var volume_db := float(params.get("volume_db", 0.0))
	var index := AudioServer.get_bus_count()  # add_bus(-1) appends to this index
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add audio bus %s" % bus_name)
	ur.add_do_method(AudioServer, "add_bus", -1)
	ur.add_do_method(AudioServer, "set_bus_name", index, bus_name)
	ur.add_do_method(AudioServer, "set_bus_volume_db", index, volume_db)
	ur.add_undo_method(AudioServer, "remove_bus", index)
	ur.commit_action()
	return _router._ok({"index": index, "name": bus_name})



func _cmd_add_audio_bus_effect(params: Dictionary) -> Dictionary:
	var bus_index := _resolve_bus_index(params.get("bus"))
	if bus_index < 0:
		return _router._fail("VALIDATION_ERROR", "No audio bus '%s'." % str(params.get("bus")))
	var effect_type := str(params.get("effect_type", ""))
	if not ClassDB.can_instantiate(effect_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % effect_type)
	var effect_obj: Object = ClassDB.instantiate(effect_type)
	if not (effect_obj is AudioEffect):
		if not (effect_obj is RefCounted):
			effect_obj.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not an AudioEffect." % effect_type)
	var effect: AudioEffect = effect_obj
	_router._apply_props(effect, params.get("properties", {}))
	var effect_index := AudioServer.get_bus_effect_count(bus_index)  # appended position
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s to bus %d" % [effect_type, bus_index])
	ur.add_do_method(AudioServer, "add_bus_effect", bus_index, effect, -1)
	ur.add_do_reference(effect)
	ur.add_undo_method(AudioServer, "remove_bus_effect", bus_index, effect_index)
	ur.commit_action()
	return _router._ok({
		"bus": String(AudioServer.get_bus_name(bus_index)),
		"bus_index": bus_index,
		"effect_type": effect_type,
		"effect_index": effect_index,
	})


## Remove an audio bus — the inverse of add_audio_bus (issue #219 G8). The Master bus
## (index 0) is never removable. Undo restores the bus with all properties + effects via
## MCPAudioBusCapture; effect resources are kept alive with add_undo_reference.
func _cmd_remove_audio_bus(params: Dictionary) -> Dictionary:
	var bus_index := _resolve_bus_index(params.get("bus"))
	if bus_index < 0:
		return _router._fail("VALIDATION_ERROR", "No audio bus '%s'." % str(params.get("bus")))
	if bus_index == 0:
		return _router._fail("VALIDATION_ERROR", "Cannot remove the Master bus.")
	var state := AudioBusCapture.capture(bus_index)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove audio bus %s" % state["name"])
	ur.add_do_method(AudioServer, "remove_bus", bus_index)
	ur.add_undo_method(self, "_restore_audio_bus", bus_index, state)
	for entry in state["effects"]:
		ur.add_undo_reference(entry["effect"])
	ur.commit_action()
	return _router._ok({"name": state["name"], "index": bus_index, "removed": true})


func _restore_audio_bus(index: int, state: Dictionary) -> void:
	AudioBusCapture.restore(index, state)


## Remove one effect from a bus — the inverse of add_audio_bus_effect (issue #219 G8).
## Undo re-inserts the captured effect (and its enabled flag) at the same index.
func _cmd_remove_audio_bus_effect(params: Dictionary) -> Dictionary:
	var bus_index := _resolve_bus_index(params.get("bus"))
	if bus_index < 0:
		return _router._fail("VALIDATION_ERROR", "No audio bus '%s'." % str(params.get("bus")))
	var effect_index := int(params.get("effect_index", -1))
	if effect_index < 0 or effect_index >= AudioServer.get_bus_effect_count(bus_index):
		return _router._fail("VALIDATION_ERROR", "No effect at index %d on bus '%s'." % [effect_index, String(AudioServer.get_bus_name(bus_index))])
	var effect := AudioServer.get_bus_effect(bus_index, effect_index)
	var enabled := AudioServer.is_bus_effect_enabled(bus_index, effect_index)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove effect %d from bus %d" % [effect_index, bus_index])
	ur.add_do_method(AudioServer, "remove_bus_effect", bus_index, effect_index)
	ur.add_undo_method(AudioServer, "add_bus_effect", bus_index, effect, effect_index)
	ur.add_undo_method(AudioServer, "set_bus_effect_enabled", bus_index, effect_index, enabled)
	ur.add_undo_reference(effect)
	ur.commit_action()
	return _router._ok({
		"bus": String(AudioServer.get_bus_name(bus_index)),
		"bus_index": bus_index,
		"effect_index": effect_index,
		"removed": true,
	})


func _resolve_bus_index(bus_ref: Variant) -> int:
	if bus_ref is int or bus_ref is float:
		var i := int(bus_ref)
		return i if (i >= 0 and i < AudioServer.get_bus_count()) else -1
	return AudioServer.get_bus_index(str(bus_ref))


