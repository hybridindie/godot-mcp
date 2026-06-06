@tool
class_name MCPRuntimeInspectHandlers
extends RefCounted
## Domain handler: runtime inspect.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_find_ui_elements"] = _cmd_find_ui_elements
	handlers["cmd_get_property_samples"] = _cmd_get_property_samples
	handlers["cmd_monitor_property"] = _cmd_monitor_property


# -- handlers ----------------------------------------------------------------

func _cmd_monitor_property(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var node_path := str(params.get("node_path", ""))
	var property := str(params.get("property", ""))
	if node_path.is_empty() or property.is_empty():
		return _router._fail("VALIDATION_ERROR", "'node_path' and 'property' are required.")
	var samples := clampi(int(params.get("samples", 30)), 1, 300)
	_router._debugger.clear_property_samples()  # drop any prior capture so get_ reflects this one
	_router._debugger.send_to_probe("godot_mcp:monitor_property", [{
		"node_path": node_path, "property": property, "samples": samples,
	}])
	return _router._ok({"monitoring": true, "node_path": node_path, "property": property, "samples": samples})



func _cmd_get_property_samples(_params: Dictionary) -> Dictionary:
	if _router._debugger == null or not _router._debugger.is_connected_to_probe():
		return _router._ok({"ready": false, "connected": false, "samples": []})
	var payload: Variant = _router._debugger.get_property_samples()
	if payload == null:
		return _router._ok({"ready": false, "connected": true, "samples": []})
	var result: Dictionary = (payload as Dictionary).duplicate()
	result["connected"] = true
	return _router._ok(result)



func _cmd_find_ui_elements(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	# Each tool invocation carries a stable request_id (constant across its poll loop). We
	# dispatch the (expensive) full-Control scan to the probe exactly once per request_id
	# and match the cached result by that id — so repeated polls don't re-scan, and reusing
	# identical filters can't return a prior request's stale result.
	var request_id := str(params.get("request_id", ""))
	var payload: Variant = _router._debugger.get_ui_elements()
	if payload is Dictionary and (payload as Dictionary).get("request_id") == request_id:
		return _router._ok({"ready": true, "elements": (payload as Dictionary).get("elements", [])})
	if _router._debugger.get_pending_ui_request() != request_id:
		_router._debugger.begin_ui_request(request_id)
		_router._debugger.send_to_probe("godot_mcp:find_ui", [{
			"name_contains": str(params.get("name_contains", "")),
			"class_filter": str(params.get("class_filter", "")),
			"visible_only": bool(params.get("visible_only", false)),
			"request_id": request_id,
		}])
	return _router._ok({"ready": false, "elements": []})


