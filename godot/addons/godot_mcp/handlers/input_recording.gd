@tool
class_name MCPInputRecordingHandlers
extends RefCounted
## Domain handler: input recording.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_get_recording"] = _cmd_get_recording
	handlers["cmd_record_input"] = _cmd_record_input
	handlers["cmd_stop_recording"] = _cmd_stop_recording


# -- handlers ----------------------------------------------------------------

func _cmd_record_input(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	_router._debugger.clear_recorded_input()  # drop any prior recording so stop reads this one
	_router._debugger.send_to_probe("godot_mcp:record_start", [{
		"include_motion": bool(params.get("include_motion", false)),
	}])
	return _router._ok({"recording": true})



func _cmd_stop_recording(_params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	# Drop any prior recording first so get_recording reflects THIS stop's push, even if
	# stop_recording is called without a preceding record_input.
	_router._debugger.clear_recorded_input()
	_router._debugger.send_to_probe("godot_mcp:record_stop", [])
	return _router._ok({"recording": false})



func _cmd_get_recording(_params: Dictionary) -> Dictionary:
	if _router._debugger == null or not _router._debugger.is_connected_to_probe():
		return _router._ok({"ready": false, "connected": false, "events": []})
	var payload: Variant = _router._debugger.get_recorded_input()
	if payload == null:
		return _router._ok({"ready": false, "connected": true, "events": []})
	return _router._ok({"ready": true, "connected": true, "events": (payload as Dictionary).get("events", [])})


