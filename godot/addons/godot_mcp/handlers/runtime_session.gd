@tool
class_name MCPRuntimeSessionHandlers
extends RefCounted
## Domain handler: runtime session.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_game_scene_tree"] = _cmd_get_game_scene_tree
	handlers["cmd_get_input_stats"] = _cmd_get_input_stats
	handlers["cmd_is_playing"] = _cmd_is_playing
	handlers["cmd_play_input_sequence"] = _cmd_play_input_sequence
	handlers["cmd_play_scene"] = _cmd_play_scene
	handlers["cmd_simulate_action"] = _cmd_simulate_action
	handlers["cmd_simulate_key"] = _cmd_simulate_key
	handlers["cmd_simulate_mouse"] = _cmd_simulate_mouse
	handlers["cmd_stop_scene"] = _cmd_stop_scene


# -- handlers ----------------------------------------------------------------

func _cmd_play_scene(params: Dictionary) -> Dictionary:
	var scene_path := str(params.get("scene_path", ""))
	if scene_path.is_empty():
		EditorInterface.play_main_scene()
	else:
		var is_scene := scene_path.ends_with(".tscn") or scene_path.ends_with(".scn")
		if not scene_path.begins_with("res://") or not is_scene:
			return _router._fail("VALIDATION_ERROR", "scene_path must be a res:// .tscn or .scn file.")
		if not FileAccess.file_exists(scene_path):
			return _router._fail("RESOURCE_NOT_FOUND", "No scene at '%s'." % scene_path)
		EditorInterface.play_custom_scene(scene_path)
	return _router._ok({
		"playing": EditorInterface.is_playing_scene(),
		"scene": EditorInterface.get_playing_scene(),
	})



func _cmd_stop_scene(_params: Dictionary) -> Dictionary:
	EditorInterface.stop_playing_scene()
	return _router._ok({"playing": EditorInterface.is_playing_scene()})



func _cmd_is_playing(_params: Dictionary) -> Dictionary:
	return _router._ok({
		"playing": EditorInterface.is_playing_scene(),
		"scene": EditorInterface.get_playing_scene(),
	})



func _cmd_get_game_scene_tree(_params: Dictionary) -> Dictionary:
	if not EditorInterface.is_playing_scene():
		return _router._fail("PRECONDITION_FAILED", "No play session. Run play_scene first.", "play_session")
	if _router._debugger == null:
		return _router._fail("INTERNAL_ERROR", "Debugger plugin is unavailable.")
	if not _router._debugger.is_connected_to_probe():
		# Playing, but the probe hasn't announced itself — usually means the consuming
		# project hasn't added the godot_mcp runtime probe autoload yet.
		return _router._ok({
			"playing": true,
			"connected": false,
			"tree": null,
			"hint": "Add the godot_mcp runtime probe (addons/godot_mcp/mcp_runtime_probe.gd) as an autoload in the game to enable live inspection.",
		})
	var tree: Variant = _router._debugger.get_cached_scene_tree()
	_router._debugger.request_scene_tree()  # refresh the cache for the next call
	return _router._ok({"playing": true, "connected": true, "tree": tree})



func _cmd_simulate_key(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	if str(params.get("key", "")).is_empty():
		return _router._fail("VALIDATION_ERROR", "'key' must be a non-empty key name.")
	_router._debugger.send_to_probe("godot_mcp:simulate_key", [params])
	return _router._ok({"sent": true, "kind": "key", "count": 1})


func _cmd_simulate_mouse(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var button := str(params.get("button", ""))
	if not _router._valid_mouse_button(button):
		return _router._fail("VALIDATION_ERROR", "'button' must be empty (motion) or one of %s." % str(["left", "right", "middle", "wheel_up", "wheel_down"]))
	_router._debugger.send_to_probe("godot_mcp:simulate_mouse", [params])
	return _router._ok({"sent": true, "kind": "mouse", "count": 1})


func _cmd_simulate_action(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	if str(params.get("action", "")).is_empty():
		return _router._fail("VALIDATION_ERROR", "'action' must be a non-empty action name.")
	_router._debugger.send_to_probe("godot_mcp:simulate_action", [params])
	return _router._ok({"sent": true, "kind": "action", "count": 1})



func _cmd_play_input_sequence(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var events: Variant = params.get("events")
	if not (events is Array) or (events as Array).is_empty():
		return _router._fail("VALIDATION_ERROR", "'events' must be a non-empty array.")
	# Validate each event's shape/type up front so the returned count is reliable and a
	# malformed event can't be silently skipped by the probe.
	for i in (events as Array).size():
		var bad := _router._invalid_input_event(events[i])
		if not bad.is_empty():
			return _router._fail("VALIDATION_ERROR", "events[%d]: %s" % [i, bad])
	_router._debugger.send_to_probe("godot_mcp:play_input_sequence", [params])
	return _router._ok({"sent": true, "kind": "sequence", "count": (events as Array).size()})


func _cmd_get_input_stats(_params: Dictionary) -> Dictionary:
	var playing := EditorInterface.is_playing_scene()
	var connected: bool = _router._debugger != null and _router._debugger.is_connected_to_probe()
	var injected: int = _router._debugger.get_input_acks() if connected else 0
	return _router._ok({"playing": playing, "connected": connected, "injected": injected})


