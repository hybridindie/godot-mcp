extends SceneTree
## Headless behavior test for runtime physics read-back (issue #599).
##
## Run via: godot --headless --path godot/ --script res://tests/physics_runtime_read_smoke.gd
##
## The Godot 4.8 read APIs (``RigidBody2D/3D.get_velocity_at_position`` and the
## non-allocating ``PhysicsDirectSpaceState2D/3D.*_into`` queries) are referenced
## through ClassDB only — never statically — so the addon still parses on the
## 4.4 floor. This smoke asserts both sides of the gate:
##
## - on 4.4–4.7 (the locally installed binary): the addon handler returns a
##   structured ``UNSUPPORTED`` envelope with an actionable "4.8" hint, and the
##   in-game probe replies ``unsupported`` too — never a crash;
## - on 4.8+: the gate opens, the guard still applies, and a real
##   ``intersect_ray_into`` query run on a physics frame against an empty space
##   returns a well-formed no-hit reply.
##
## It also drives the probe's one-shot physics queue end to end (enqueue →
## ``_physics_process`` → reply), which is the deferral that keeps queries inside
## a physics frame. Prints PHYSICS_RUNTIME_READ_TEST_OK, quits 0.

const Router := preload("res://addons/godot_mcp/command_router.gd")
const Probe := preload("res://addons/godot_mcp/mcp_runtime_probe.gd")

var _failures: Array[String] = []
var _router: Object
var _probe: Node
var _supports_query_3d := false
var _physics_frame_checked := false


func _initialize() -> void:
	_router = Router.new()
	# Headless has no editor play session: pin the oracle false so the 4.8 branch
	# exercises the guard deterministically instead of touching EditorInterface.
	_router._guards.set_play_session_oracle(func() -> bool: return false)
	# Drive the registered handlers (registration is part of what this smoke pins;
	# a direct preload would also hit the router<->handler cyclic class reference).
	var velocity_handler: Callable = _router._handlers.get("cmd_get_velocity_at_point", Callable())
	var query_handler: Callable = _router._handlers.get("cmd_physics_space_query", Callable())

	var supports_velocity := (
		ClassDB.class_has_method("RigidBody2D", "get_velocity_at_position")
		and ClassDB.class_has_method("RigidBody3D", "get_velocity_at_position")
		and ClassDB.class_has_method("RigidBody2D", "get_velocity_at_local_position")
		and ClassDB.class_has_method("RigidBody3D", "get_velocity_at_local_position")
	)
	var supports_query_2d := (
		ClassDB.class_exists("PhysicsIntersectRayResult2D")
		and ClassDB.class_has_method("PhysicsDirectSpaceState2D", "intersect_ray_into")
	)
	_supports_query_3d = (
		ClassDB.class_exists("PhysicsIntersectRayResult3D")
		and ClassDB.class_has_method("PhysicsDirectSpaceState3D", "intersect_ray_into")
	)

	# --- editor-side handler gate -------------------------------------------
	var velocity: Dictionary = {}
	if velocity_handler.is_valid():
		velocity = velocity_handler.call({
			"node_path": "/root/Body", "point": {"x": 0.0, "y": 0.0}, "request_id": "v1",
		})
	else:
		_failures.append("cmd_get_velocity_at_point is not registered")
	if supports_velocity:
		_neq("velocity_48_not_unsupported", velocity.get("error"), "UNSUPPORTED")
	else:
		_eq("velocity_47_unsupported", velocity.get("error"), "UNSUPPORTED")
		_contains("velocity_hint_names_48", str(velocity.get("hint", "")), "4.8")

	var query: Dictionary = {}
	if query_handler.is_valid():
		query = query_handler.call({
			"method": "intersect_ray",
			"dimension": "2d",
			"node_path": "",
			"query": {"from": {"x": 0.0, "y": 0.0}, "to": {"x": 10.0, "y": 0.0}},
			"request_id": "q1",
		})
	else:
		_failures.append("cmd_physics_space_query is not registered")
	if supports_query_2d:
		_neq("query_48_not_unsupported", query.get("error"), "UNSUPPORTED")
	else:
		_eq("query_47_unsupported", query.get("error"), "UNSUPPORTED")
		_contains("query_hint_names_48", str(query.get("hint", "")), "4.8")

	# --- in-game probe: velocity reply + one-shot queue ---------------------
	_probe = Node.new()
	_probe.name = "MCPRuntimeProbe"
	_probe.set_script(Probe)
	root.add_child(_probe)

	var probe_velocity: Dictionary = _probe._run_physics_request("velocity_at_point", {
		"request_id": "pv1",
		"node_path": "/root/Nope",
		"point": {"x": 0.0, "y": 0.0},
		"local": false,
	})
	_eq("probe_velocity_request_id", probe_velocity.get("request_id"), "pv1")
	if supports_velocity:
		_contains(
			"probe_velocity_structured_node_error",
			str(probe_velocity.get("error", "")),
			"node not found",
		)
	else:
		_eq("probe_velocity_unsupported", probe_velocity.get("unsupported"), true)

	# The capture handler only enqueues; _physics_process answers in a physics frame.
	_probe._capture("get_velocity_at_point", [{
		"request_id": "pv-queued", "node_path": "/root/Nope", "point": {"x": 0.0, "y": 0.0},
	}])
	_eq("probe_queue_holds_request", _probe._physics_queue.size(), 1)
	_probe._physics_process(0.016)
	_eq("probe_queue_drained", _probe._physics_queue.size(), 0)
	_eq("probe_queue_reply_request_id", _probe._last_physics_reply.get("request_id"), "pv-queued")


## The space-state query must run on a physics frame — this callback is the real
## one, mirroring the probe's deferral (asserted on both 4.7 and 4.8).
func _physics_process(_delta: float) -> bool:
	if _physics_frame_checked:
		return false
	_physics_frame_checked = true
	var probe_query: Dictionary = _probe._run_physics_request("physics_space_query", {
		"request_id": "pq1",
		"method": "intersect_ray",
		"dimension": "3d",
		"node_path": "",
		"query": {
			"from": {"x": 0.0, "y": 100.0, "z": 0.0},
			"to": {"x": 0.0, "y": -100.0, "z": 0.0},
		},
		"max_results": 8,
	})
	_eq("probe_query_request_id", probe_query.get("request_id"), "pq1")
	if _supports_query_3d:
		_neq("probe_query_48_not_unsupported", probe_query.get("unsupported", false), true)
		if str(probe_query.get("error", "")).is_empty():
			# A real intersect_ray_into against the empty world: no hit, no crash.
			_eq("probe_query_empty_space_hit", probe_query.get("hit"), false)
			_eq("probe_query_empty_space_count", probe_query.get("count"), 0)
			_eq("probe_query_empty_space_results", probe_query.get("results"), [])
		else:
			# A missing world is reported structurally, never as a crash.
			_contains(
				"probe_query_structural_error",
				str(probe_query.get("error")),
				"physics space",
			)
	else:
		_eq("probe_query_unsupported", probe_query.get("unsupported"), true)
	_finish()
	return false


func _finish() -> void:
	# Break the router<->handler reference cycle so the headless run exits clean.
	_router.dispose()
	_probe.queue_free()
	if _failures.is_empty():
		print("PHYSICS_RUNTIME_READ_TEST_OK")
		quit(0)
	else:
		for failure in _failures:
			printerr("FAIL: %s" % failure)
		print("PHYSICS_RUNTIME_READ_TEST_FAIL")
		quit(1)


func _eq(what: String, got: Variant, expected: Variant) -> void:
	if typeof(got) != typeof(expected) or got != expected:
		_failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


func _neq(what: String, got: Variant, unexpected: Variant) -> void:
	if typeof(got) == typeof(unexpected) and got == unexpected:
		_failures.append("%s: should not be %s" % [what, str(unexpected)])


func _contains(what: String, text: String, needle: String) -> void:
	if not text.contains(needle):
		_failures.append("%s: '%s' does not contain '%s'" % [what, text, needle])
