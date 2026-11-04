@tool
class_name MCPRuntimeInspectHandlers
extends RefCounted
## Domain handler: runtime inspect.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter

# #599: 4.8 runtime physics read-back capability gate + query vocabulary, shared
# with the in-game probe. ClassDB-based (never a static 4.8 reference), so the
# addon still parses on the 4.4 floor.
const PhysicsRead := preload("../physics_read.gd")


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_find_ui_elements"] = _cmd_find_ui_elements
	handlers["cmd_get_property_samples"] = _cmd_get_property_samples
	handlers["cmd_get_velocity_at_point"] = _cmd_get_velocity_at_point
	handlers["cmd_monitor_property"] = _cmd_monitor_property
	handlers["cmd_physics_space_query"] = _cmd_physics_space_query
	handlers["cmd_read_property"] = _cmd_read_property


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
	# #536 push-on-change sampling defaults on; the probe dedupes unchanged values
	# (epsilon-tolerant for floats) unless the caller pins the legacy behavior.
	var on_change_only := bool(params.get("on_change_only", true))
	var epsilon := float(params.get("epsilon", 0.0001))
	_router._debugger.clear_property_samples()  # drop any prior capture so get_ reflects this one
	_router._debugger.send_to_probe("godot_mcp:monitor_property", [{
		"node_path": node_path, "property": property, "samples": samples,
		"on_change_only": on_change_only, "epsilon": epsilon,
	}])
	return _router._ok({
		"monitoring": true, "node_path": node_path, "property": property, "samples": samples,
		"on_change_only": on_change_only, "epsilon": epsilon,
	})



func _cmd_get_property_samples(_params: Dictionary) -> Dictionary:
	if _router._debugger == null or not _router._debugger.is_connected_to_probe():
		return _router._ok({"ready": false, "connected": false, "samples": []})
	var payload: Variant = _router._debugger.get_property_samples()
	if payload == null:
		# #459: the monitor is registered but no sample batch has landed yet.
		return _router._ok({
			"ready": false, "connected": true, "samples": [], "reason": "capture_pending",
		})
	var result: Dictionary = (payload as Dictionary).duplicate()
	result["connected"] = true
	return _router._ok(result)



# #571: dedicated one-shot read — reads the live value NOW via the probe's
# read_property message and never touches the monitor slot, so a one-shot
# assert (assert_node_state) cannot replace a running monitor_property capture.
# Same request_id + poll pattern as find_ui_elements: the reply lands in the
# debugger cache on a later frame via _capture; the caller polls until ready.
func _cmd_read_property(params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var node_path := str(params.get("node_path", ""))
	var property := str(params.get("property", ""))
	if node_path.is_empty() or property.is_empty():
		return _router._fail("VALIDATION_ERROR", "'node_path' and 'property' are required.")
	var request_id := str(params.get("request_id", ""))
	if request_id.is_empty():
		return _router._fail("VALIDATION_ERROR", "'request_id' is required.")
	if _router._debugger.get_pending_read_request() != request_id:
		_router._debugger.begin_read_request(request_id)
		_router._debugger.send_to_probe("godot_mcp:read_property", [{
			"node_path": node_path, "property": property, "request_id": request_id,
		}])
	var payload: Variant = _router._debugger.get_read_property()
	# Qodo review (#575): belt-and-braces id match — the cache is already gated
	# on the pending request_id in _capture; re-verify here so a stale reply can
	# never be served as this request's result.
	if payload is Dictionary and (payload as Dictionary).get("request_id") == request_id:
		return _router._ok(payload)
	# #459: dispatched to the probe; the reply lands on a later frame.
	return _router._ok({"ready": false, "reason": "read_pending"})



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
	# #459: the scan is dispatched to the probe and runs over the next frames.
	return _router._ok({"ready": false, "elements": [], "reason": "scan_in_flight"})


# -- runtime physics read-back (issue #599) -----------------------------------

func _cmd_get_velocity_at_point(params: Dictionary) -> Dictionary:
	# 4.8 gate first: an older editor must say UNSUPPORTED (and how to work
	# around it), not fail later inside the game.
	var unsupported_hint := PhysicsRead.velocity_hint()
	if not unsupported_hint.is_empty():
		return _router._fail("UNSUPPORTED", unsupported_hint)
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var node_path := str(params.get("node_path", ""))
	var point: Variant = params.get("point")
	var request_id := str(params.get("request_id", ""))
	if node_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "'node_path' is required.")
	if not (point is Dictionary or point is Array or point is String):
		return _router._fail(
			"VALIDATION_ERROR",
			"'point' must be a {x, y[, z]} object (or an [x, y[, z]] array).",
		)
	if point is Dictionary and not ((point as Dictionary).has("x") and (point as Dictionary).has("y")):
		return _router._fail("VALIDATION_ERROR", "'point' must contain x and y.")
	if point is Array and (point as Array).size() < 2:
		return _router._fail("VALIDATION_ERROR", "'point' must be [x, y] or [x, y, z].")
	if request_id.is_empty():
		return _router._fail("VALIDATION_ERROR", "'request_id' is required.")
	var payload: Variant = _router._debugger.get_velocity_at_point()
	if payload is Dictionary and str((payload as Dictionary).get("request_id", "")) == request_id:
		return _serve_physics_reply(payload)
	if _router._debugger.get_pending_velocity_request() != request_id:
		_router._debugger.begin_velocity_request(request_id)
		_router._debugger.send_to_probe("godot_mcp:get_velocity_at_point", [{
			"node_path": node_path,
			"point": point,
			"local": bool(params.get("local", false)),
			"request_id": request_id,
		}])
	# #459: dispatched to the probe; the reply lands on a later physics frame.
	return _router._ok({"ready": false, "reason": "velocity_pending"})


func _cmd_physics_space_query(params: Dictionary) -> Dictionary:
	var method := str(params.get("method", ""))
	if not PhysicsRead.QUERY_METHODS.has(method):
		return _router._fail(
			"VALIDATION_ERROR",
			"'method' must be one of %s." % str(PhysicsRead.QUERY_METHODS.keys()),
		)
	var dimension := str(params.get("dimension", "2d"))
	if dimension != "2d" and dimension != "3d":
		return _router._fail("VALIDATION_ERROR", "'dimension' must be '2d' or '3d'.")
	var unsupported_hint := PhysicsRead.space_query_hint(method, dimension)
	if not unsupported_hint.is_empty():
		return _router._fail("UNSUPPORTED", unsupported_hint)
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	var request_id := str(params.get("request_id", ""))
	if request_id.is_empty():
		return _router._fail("VALIDATION_ERROR", "'request_id' is required.")
	var payload: Variant = _router._debugger.get_space_query()
	if payload is Dictionary and str((payload as Dictionary).get("request_id", "")) == request_id:
		return _serve_physics_reply(payload)
	if _router._debugger.get_pending_space_query() != request_id:
		_router._debugger.begin_space_query(request_id)
		_router._debugger.send_to_probe("godot_mcp:physics_space_query", [{
			"method": method,
			"dimension": dimension,
			"node_path": str(params.get("node_path", "")),
			"query": params.get("query", {}),
			"exclude": params.get("exclude", []),
			"shape_type": str(params.get("shape_type", "")),
			"shape_properties": params.get("shape_properties", {}),
			"max_results": clampi(int(params.get("max_results", 32)), 1, 1024),
			"request_id": request_id,
		}])
	# #459: dispatched to the probe; the reply lands on a later physics frame.
	return _router._ok({"ready": false, "reason": "query_pending"})


## Serve a cached probe reply. A probe-side capability refusal becomes the same
## structured UNSUPPORTED envelope the editor-side gate emits (defence in depth:
## a game running a 4.7 probe behind a 4.8 editor, or vice versa).
func _serve_physics_reply(payload: Dictionary) -> Dictionary:
	if bool(payload.get("unsupported", false)):
		return _router._fail("UNSUPPORTED", str(payload.get("hint", "")))
	var body: Dictionary = payload.duplicate()
	body.erase("unsupported")
	body.erase("hint")
	return _router._ok(body)


