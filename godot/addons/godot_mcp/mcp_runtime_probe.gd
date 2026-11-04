extends Node
## godot-mcp runtime probe (issue #66). Runs **in the game**, not the editor.
##
## Add this script as an autoload in the *consuming* game's project to enable godot-mcp
## live runtime inspection/input while the game runs from the editor. It registers an
## EngineDebugger message capture on the "godot_mcp" channel and answers queries from the
## addon's MCPDebugger (editor side). It does nothing outside a debug session, so it is
## safe to leave enabled (it no-ops in exported/non-debug builds).
##
## The probe self-checks ``force_break`` every frame (see _process), so games
## need no cooperation; ``check_force_break`` stays public for games that want
## to break at a chosen point in their own loop instead.

const MAX_DEPTH := 32
# #641: share the editor's JSON coercion (single implementation of the shapes).
const Coerce := preload("type_coerce.gd")
# #599: Godot 4.8 runtime physics read-back capability gate + query vocabulary
# (shared with the editor handlers; ClassDB-only so the 4.4 floor still parses).
const PhysicsRead := preload("physics_read.gd")

var force_break_pending: bool = false  ## Set true by the editor via force_break message.


## Check if the editor has requested a force_break and trigger ``breakpoint`` if so.
## Call this from the game's ``_process`` or ``_physics_process`` loop. Returns
## ``true`` if a break was triggered, ``false`` otherwise.
func check_force_break() -> bool:
	if force_break_pending:
		force_break_pending = false
		breakpoint
		return true
	return false



func _ready() -> void:
	# #565: keep processing while the game's SceneTree is paused — games pause
	# routinely (pause menus, death screens, dialogue) and this probe's frame
	# grabs / property monitors / force-break check all defer to _process; an
	# INHERIT node under a paused tree stops and every capture starves into a
	# tool timeout. It only answers debugger messages, so ALWAYS is safe.
	process_mode = Node.PROCESS_MODE_ALWAYS
	if EngineDebugger.is_active():
		EngineDebugger.register_message_capture("godot_mcp", _capture)
		_register_output_logger()
		EngineDebugger.send_message("godot_mcp:ready", [])


func _exit_tree() -> void:
	# PR #547 review: the Logger outlives the probe unless removed — on a
	# play/stop/replay cycle the autoload is freed and re-instantiated, and a
	# stale registered logger would keep sinking into a dead ring (duplicate
	# entries across sessions, and a leaked OS-level logger). Remove it in the
	# same EngineDebugger-active gate we registered it under.
	if _output_logger != null and EngineDebugger.is_active() and OS.has_method("remove_logger"):
		OS.call("remove_logger", _output_logger)
		_output_logger = null
	_output_lock.lock()
	_output_ring.clear()
	_output_lock.unlock()


## Capture handler: the "godot_mcp:" prefix is stripped before this is called.
func _capture(message: String, data: Array) -> bool:
	match message:
		"ping":
			EngineDebugger.send_message("godot_mcp:pong", [])
			return true
		"get_output":
			EngineDebugger.send_message("godot_mcp:game_output", [_output_snapshot()])
			return true
		"get_scene_tree":
			# #670: echo the request_id so the editor serves a reply only to the
			# poll that asked for it (never the previous call's tree).
			EngineDebugger.send_message("godot_mcp:scene_tree", [{
				"request_id": str(_payload(data).get("request_id", "")),
				"tree": _serialize_tree(),
			}])
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
		"read_property":
			# #571: dedicated one-shot read — reads the value now and replies
			# immediately, never touching the monitor slot, so a one-shot assert
			# cannot replace a running monitor_property capture.
			EngineDebugger.send_message("godot_mcp:read_property", [_read_property(_payload(data))])
			return true
		"get_velocity_at_point":
			# #599: velocity-at-arbitrary-point reads only on a physics frame; the
			# request is queued and answered from _physics_process (never inline).
			_enqueue_physics("velocity_at_point", _payload(data))
			return true
		"physics_space_query":
			# #599: non-allocating space-state queries have the same physics-frame
			# requirement — queue and answer from _physics_process.
			_enqueue_physics("physics_space_query", _payload(data))
			return true
		"find_ui":
			EngineDebugger.send_message("godot_mcp:ui_elements", [_find_ui(_payload(data))])
			return true
		"record_start":
			_record_start(_payload(data))
			return true
		"record_stop":
			_record_stop()
			return true
		"get_performance":
			# #670: echo the request_id (same request-scoping as get_scene_tree).
			EngineDebugger.send_message("godot_mcp:performance", [{
				"request_id": str(_payload(data).get("request_id", "")),
				"monitors": _performance_snapshot(),
			}])
			return true
		"evaluate":
			# #677: expression evaluation runs in the game via Expression (the editor
			# debugger's paused-frame eval protocol is not exposed to plugins). Echo
			# the request_id so the editor serves the reply to the right poll.
			EngineDebugger.send_message("godot_mcp:evaluation", [_evaluate(_payload(data))])
			return true
		"capture_frame":
			# Deferred one rendered frame: an inline texture read-back can return the
			# previous frame (or stall); the grab runs in _process and replies when done.
			_frame_request_id = str(_payload(data).get("request_id", ""))
			_frame_pending = true
			return true
		"clear_breakpoints":
			EngineDebugger.clear_breakpoints()
			return true
		"force_break":
			# Set a flag that the game can check in its _process loop.
			# Calling EngineDebugger.debug() from inside _capture() deadlocks
			# because debug() blocks until the editor replies with continue/step.
			force_break_pending = true
			EngineDebugger.send_message("godot_mcp:force_break_ack", [])
			print("[MCPRuntimeProbe] force_break_pending SET to true")
			return true
	return false


# --- profiling (issue #38) -------------------------------------------------

# Same curated monitors as the editor side (command_router._PERF_MONITORS).
const _PERF_MONITORS := {
	"fps": Performance.TIME_FPS,
	"process_time": Performance.TIME_PROCESS,
	"physics_process_time": Performance.TIME_PHYSICS_PROCESS,
	"memory_static": Performance.MEMORY_STATIC,
	"memory_static_max": Performance.MEMORY_STATIC_MAX,
	"object_count": Performance.OBJECT_COUNT,
	"node_count": Performance.OBJECT_NODE_COUNT,
	"resource_count": Performance.OBJECT_RESOURCE_COUNT,
	"orphan_node_count": Performance.OBJECT_ORPHAN_NODE_COUNT,
	"objects_drawn": Performance.RENDER_TOTAL_OBJECTS_IN_FRAME,
	"primitives_drawn": Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME,
	"draw_calls": Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME,
	"video_mem_used": Performance.RENDER_VIDEO_MEM_USED,
	"texture_mem_used": Performance.RENDER_TEXTURE_MEM_USED,
	"buffer_mem_used": Performance.RENDER_BUFFER_MEM_USED,
	"physics_2d_active": Performance.PHYSICS_2D_ACTIVE_OBJECTS,
	"physics_3d_active": Performance.PHYSICS_3D_ACTIVE_OBJECTS,
}


func _performance_snapshot() -> Dictionary:
	var monitors: Dictionary = {}
	for name in _PERF_MONITORS:
		monitors[name] = Performance.get_monitor(_PERF_MONITORS[name])
	return monitors


# --- game frame capture (issue #446) ----------------------------------------

var _frame_request_id := ""
var _frame_pending := false


## Grab the game's root viewport on the next rendered frame and push it to the
## editor as base64 PNG. Runs in _process (outside _capture) so the read-back
## happens after this frame has been drawn.
func _grab_frame() -> void:
	var viewport := get_viewport()
	var err := ""
	var image: Image = null
	if viewport == null:
		err = "Game viewport is unavailable."
	else:
		var texture := viewport.get_texture()
		if texture == null:
			err = "No viewport texture (no rendered frame)."
		else:
			image = texture.get_image()
			if image == null or image.is_empty():
				err = "Could not capture the game viewport image."
	if err.is_empty():
		EngineDebugger.send_message("godot_mcp:game_frame", [{
			"request_id": _frame_request_id,
			"format": "png",
			"width": image.get_width(),
			"height": image.get_height(),
			"base64": Marshalls.raw_to_base64(image.save_png_to_buffer()),
		}])
	else:
		# An error result still closes the request so the poller doesn't spin.
		EngineDebugger.send_message("godot_mcp:game_frame", [{
			"request_id": _frame_request_id,
			"ready": true,
			"error": err,
		}])


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
	var key := OS.find_keycode_from_string(str(d.get("key", "")))
	# #570: set BOTH keycodes like real hardware events do. The Input Map editor
	# binds actions by physical keycode by default, and an event carrying only
	# `keycode` never matches such a binding (docs: comparison is keycode →
	# physical_keycode, first match wins). `physical_keycode` here is the key's
	# US-QWERTY position, exactly what a real keypress reports.
	event.keycode = key
	event.physical_keycode = key
	event.pressed = bool(d.get("pressed", true))
	event.shift_pressed = bool(d.get("shift", false))
	event.ctrl_pressed = bool(d.get("ctrl", false))
	event.alt_pressed = bool(d.get("alt", false))
	event.meta_pressed = bool(d.get("meta", false))
	# device left at default 0. Verified on Godot 4.7 (GH-116274 made real keyboard
	# events device=16 / mouse=32) that injected events still reach _input/
	# _unhandled_input and update InputMap action state — tests/input_inject_smoke.gd.
	# #570: keycode + physical_keycode are both set, so bindings of either type fire.
	Input.parse_input_event(event)
	_ack()


func _inject_mouse(d: Dictionary) -> void:
	var position := Vector2(float(d.get("x", 0.0)), float(d.get("y", 0.0)))
	var button_name := str(d.get("button", ""))
	# device left at default 0 on the synthesized events below — injection verified
	# on Godot 4.7 (GH-116274), see the _inject_key note and input_inject_smoke.gd.
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
# #536 push-on-change state: last queued value (JSON-safe) for the change test,
# the epsilon used for float comparisons, and frames since the last queued sample.
var _monitor_last_value: Variant = null
var _monitor_last_queued_frame := -1
var _monitor_epsilon := 0.0001
var _monitor_on_change_only := true
var _monitor_requested := 0
# #536 probe self-timing: cumulative microseconds spent sampling (get + change
# test + queue), so the profiling surface can measure the frame-time win.
var _monitor_sampling_usec := 0
var _monitor_dropped_duplicates := 0


## Sample the monitored property once per frame until the requested count is reached,
## then push the completed series to the editor (bounded capture — no perpetual stream).
## #536: with on_change_only (default) a sample is queued only when the JSON-coerced
## value differs from the last queued one — exact for non-floats, epsilon-tolerant for
## floats — and duplicates are dropped (counted). The capture still ends after
## `samples` frames, so the series may hold fewer entries than requested.
## Also services force_break: an editor-requested break fires here (one ``breakpoint``
## inside this frame), so the game needs no cooperation.
func _process(_delta: float) -> void:
	if _frame_pending:
		_frame_pending = false
		_grab_frame()
		return  # this frame's read-back replaces the sample pass
	if check_force_break():
		return  # resumed after the break; skip this frame's sample so monitors freeze while paused
	if _monitor_remaining <= 0:
		return
	_monitor_remaining -= 1
	var node := get_node_or_null(_monitor_target)
	if node == null:
		_monitor_error = "node not found at '%s'" % String(_monitor_target)
		_monitor_remaining = 0
	else:
		var sample_start := Time.get_ticks_usec()
		var value := Coerce.to_json(node.get(_monitor_property))
		if _should_queue_sample(value, Engine.get_process_frames()):
			_monitor_samples.append({
				"frame": Engine.get_process_frames(),
				"value": value,
			})
		_monitor_sampling_usec += Time.get_ticks_usec() - sample_start
	if _monitor_remaining <= 0:
		_push_samples()


## The #536 push-on-change decision for one frame's reading: queue when the value
## differs from the last queued one (exact for non-floats, epsilon-tolerant for
## floats) — or always, when legacy on_change_only=false. Unchanged readings are
## dropped and counted (honest stats, never silent). Updates the last-value state.
func _should_queue_sample(value: Variant, frame: int) -> bool:
	var changed := not _values_equal(value, _monitor_last_value, _monitor_epsilon)
	if _monitor_on_change_only and not changed:
		_monitor_dropped_duplicates += 1
		return false
	_monitor_last_value = value
	_monitor_last_queued_frame = frame
	return true


## Value equality for the #536 change test: floats compare within `epsilon`
## (recursively for the dict/array shapes Coerce.to_json emits), everything else
## compares exactly. A float inside a Vector2/Color dict differs when any
## component exceeds epsilon. Mismatched types are always a difference — GDScript
## raises on `==` between mismatched operand types (e.g. int vs String), so the
## type check precedes the comparison.
func _values_equal(a: Variant, b: Variant, epsilon: float) -> bool:
	if typeof(a) != typeof(b):
		return false
	if typeof(a) == TYPE_FLOAT:
		return absf(a - b) <= epsilon
	if typeof(a) == TYPE_DICTIONARY:
		if (a as Dictionary).size() != (b as Dictionary).size():
			return false
		for key in a:
			if not (b as Dictionary).has(key):
				return false
			if not _values_equal(a[key], b[key], epsilon):
				return false
		return true
	if typeof(a) == TYPE_ARRAY:
		if (a as Array).size() != (b as Array).size():
			return false
		for i in range((a as Array).size()):
			if not _values_equal(a[i], b[i], epsilon):
				return false
		return true
	return a == b


## #677: evaluate a GDScript expression in the running game via Expression.
## The editor debugger's paused-frame eval protocol is not exposed to editor
## debugger plugins on Godot 4.7, so evaluation runs in-game instead (the base
## instance is the scene root; it is not frame-scoped). Returns the JSON-safe
## value, or an `error` string on parse/execute failure — never silent.
func _evaluate(d: Dictionary) -> Dictionary:
	var expression := str(d.get("expression", ""))
	var request_id := str(d.get("request_id", ""))
	var result := {
		"request_id": request_id, "expression": expression,
		"value": null, "evaluated": true, "error": "",
	}
	if expression.is_empty():
		result["error"] = "empty expression"
		return result
	var expr := Expression.new()
	if expr.parse(expression) != OK:
		result["error"] = "parse error: %s" % expr.get_error_text()
		return result
	var value: Variant = expr.execute([], get_tree().root, false)
	if expr.has_execute_failed():
		result["error"] = "evaluation failed: %s" % expr.get_error_text()
		return result
	result["value"] = Coerce.to_json(value)
	return result


## #571 one-shot read: resolve the node, read the property once, reply now.
## Uses the same JSON-safe coercion as the monitor series and the same
## read-property semantics (built-ins + script vars), but shares no state with
## the monitor slot — a capture in progress keeps capturing.
func _read_property(d: Dictionary) -> Dictionary:
	var node_path := str(d.get("node_path", ""))
	var property := str(d.get("property", ""))
	var request_id := str(d.get("request_id", ""))
	var node := get_node_or_null(NodePath(node_path))
	if node == null:
		return {
			"request_id": request_id, "node_path": node_path, "property": property,
			"value": null, "error": "node not found at '%s'" % node_path, "ready": true,
		}
	if not (property in node):
		return {
			"request_id": request_id, "node_path": node_path, "property": property,
			"value": null, "error": "no property '%s' on the node" % property, "ready": true,
		}
	return {
		"request_id": request_id, "node_path": node_path, "property": property,
		"value": Coerce.to_json(node.get(property)), "error": "", "ready": true,
	}


# --- runtime physics read-back (issue #599) ---------------------------------
#
# Both reads are 4.8-only and must run on a physics frame, so _capture only
# enqueues and _physics_process answers one request per frame. The 4.8 APIs are
# reached through ClassDB/call() — a static reference would break the 4.4 parse.

const PHYSICS_QUEUE_MAX := 8

var _physics_queue: Array = []
## Last reply produced by _physics_process (smoke-test seam; also handy in a
## debugger). Never sent over the bridge as-is.
var _last_physics_reply: Dictionary = {}


func _enqueue_physics(kind: String, d: Dictionary) -> void:
	if _physics_queue.size() >= PHYSICS_QUEUE_MAX:
		# Bounded and honest: a full queue is reported, never silently dropped.
		_send_physics_reply(kind, {
			"request_id": str(d.get("request_id", "")),
			"ready": true,
			"error": "physics query queue is full (%d pending); retry in a frame." % PHYSICS_QUEUE_MAX,
		})
		return
	_physics_queue.append({"kind": kind, "params": d})


## Answer one queued physics read per physics frame (never from _capture, and
## never more than one — a query that blocks the game thread is worse than slow).
func _physics_process(_delta: float) -> void:
	if _physics_queue.is_empty():
		return
	var request: Dictionary = _physics_queue.pop_front()
	var reply := _run_physics_request(str(request.get("kind", "")), request.get("params", {}))
	_send_physics_reply(str(request.get("kind", "")), reply)


func _send_physics_reply(kind: String, reply: Dictionary) -> void:
	_last_physics_reply = reply
	if not EngineDebugger.is_active():
		return  # headless smoke / exported build: no debugger channel to answer on
	var channel := "velocity_at_point" if kind == "velocity_at_point" else "physics_space_query"
	EngineDebugger.send_message("godot_mcp:" + channel, [reply])


## Produce one reply dict (also called directly by the headless smoke).
func _run_physics_request(kind: String, d: Dictionary) -> Dictionary:
	if kind == "velocity_at_point":
		return _velocity_at_point(d)
	if kind == "physics_space_query":
		return _physics_space_query(d)
	return {
		"request_id": str(d.get("request_id", "")),
		"ready": true,
		"error": "unknown physics read request '%s'." % kind,
	}


## Velocity at an arbitrary point on a live RigidBody2D/3D (Godot 4.8+).
func _velocity_at_point(d: Dictionary) -> Dictionary:
	var request_id := str(d.get("request_id", ""))
	var node_path := str(d.get("node_path", ""))
	var reply := {
		"request_id": request_id, "ready": true, "node_path": node_path,
		"node_class": "", "dimension": "", "local": bool(d.get("local", false)),
		"point": {}, "velocity": {}, "error": "",
	}
	if not PhysicsRead.velocity_supported():
		return _unsupported_physics_reply(reply, PhysicsRead.velocity_hint())
	var node := get_node_or_null(NodePath(node_path))
	if node == null:
		reply["error"] = "node not found at '%s'" % node_path
		return reply
	var dimension := ""
	if node is RigidBody2D:
		dimension = "2d"
	elif node is RigidBody3D:
		dimension = "3d"
	if dimension.is_empty():
		reply["error"] = "node at '%s' is %s, not a RigidBody2D or RigidBody3D" % [
			node_path, node.get_class(),
		]
		return reply
	var engine_method := (
		"get_velocity_at_local_position" if bool(d.get("local", false))
		else "get_velocity_at_position"
	)
	if not node.has_method(engine_method):
		return _unsupported_physics_reply(reply, PhysicsRead.velocity_hint())
	if not _has_point_components(d.get("point")):
		reply["error"] = "'point' must contain x and y (a {x, y[, z]} object or an [x, y[, z]] array)."
		return reply
	var point: Variant = _physics_vector(d.get("point"), dimension)
	reply["node_class"] = node.get_class()
	reply["dimension"] = dimension
	reply["point"] = Coerce.to_json(point)
	reply["velocity"] = Coerce.to_json(node.call(engine_method, point))
	return reply


## A non-allocating PhysicsDirectSpaceState2D/3D *_into query (Godot 4.8+).
func _physics_space_query(d: Dictionary) -> Dictionary:
	var method := str(d.get("method", ""))
	var dimension := str(d.get("dimension", "2d"))
	var reply := {
		"request_id": str(d.get("request_id", "")), "ready": true,
		"method": method, "dimension": dimension, "hit": false, "count": 0,
		"results": [], "safe_fraction": null, "unsafe_fraction": null, "error": "",
	}
	if not PhysicsRead.QUERY_METHODS.has(method):
		reply["error"] = "unknown physics space query method '%s'." % method
		return reply
	if not PhysicsRead.space_query_supported(method, dimension):
		return _unsupported_physics_reply(
			reply, PhysicsRead.space_query_hint(method, dimension)
		)
	var node_path := str(d.get("node_path", ""))
	if not node_path.is_empty() and get_node_or_null(NodePath(node_path)) == null:
		reply["error"] = "node not found at '%s'" % node_path
		return reply
	var space_state: Variant = _space_state(dimension, node_path)
	if space_state == null:
		reply["error"] = "physics space is unavailable (no active World%s)." % dimension.to_upper()
		return reply
	var built := _build_space_query(method, dimension, d)
	if not bool(built.get("ok", false)):
		reply["error"] = str(built.get("error", "could not build the physics query."))
		return reply
	var hit: Variant = space_state.call(
		str(PhysicsRead.QUERY_METHODS[method]), built["query"], built["result"]
	)
	reply["hit"] = bool(hit)
	_collect_space_query_results(method, built["result"], reply)
	return reply


func _unsupported_physics_reply(reply: Dictionary, hint: String) -> Dictionary:
	# The editor handler turns this into the structured UNSUPPORTED envelope; the
	# flag exists so a 4.8 editor with an older copied probe still fails honestly.
	reply["unsupported"] = true
	reply["hint"] = hint
	reply["error"] = hint
	return reply


func _physics_vector(raw: Variant, dimension: String) -> Variant:
	if dimension == "3d":
		return Coerce.from_json(raw, TYPE_VECTOR3)
	return Coerce.from_json(raw, TYPE_VECTOR2)


## A point is usable when it carries x/y explicitly (or is a non-empty string
## form). An empty dict would silently become the origin — refuse instead.
func _has_point_components(raw: Variant) -> bool:
	if raw is Dictionary:
		return (raw as Dictionary).has("x") and (raw as Dictionary).has("y")
	if raw is Array:
		return (raw as Array).size() >= 2
	if raw is String:
		return not (raw as String).strip_edges().is_empty()
	return false


## Resolve the 2D/3D space state for the target world (a node's world, or the
## root viewport's when node_path is empty). Null when no world is available.
func _space_state(dimension: String, node_path: String) -> Variant:
	var node := get_node_or_null(NodePath(node_path)) if not node_path.is_empty() else null
	if dimension == "3d":
		if node is Node3D and node.get_world_3d() != null:
			return node.get_world_3d().direct_space_state
		var viewport_3d := get_viewport()
		if viewport_3d != null and viewport_3d.world_3d != null:
			return viewport_3d.world_3d.direct_space_state
		return null
	if node is CanvasItem and node.get_world_2d() != null:
		return node.get_world_2d().direct_space_state
	var viewport_2d := get_viewport()
	if viewport_2d != null and viewport_2d.world_2d != null:
		return viewport_2d.world_2d.direct_space_state
	return null


## Build the existing Physics*QueryParameters object + the preallocated typed
## result object, coercing every JSON value through type_coerce.gd.
func _build_space_query(method: String, dimension: String, d: Dictionary) -> Dictionary:
	var suffix := "2D" if dimension == "2d" else "3D"
	var family := str(PhysicsRead.QUERY_PARAMETER_FAMILIES[method])
	var query_class := "Physics%sQueryParameters%s" % [family, suffix]
	var result_class := str(PhysicsRead.QUERY_RESULTS[method]) + suffix
	var query: Variant = ClassDB.instantiate(query_class)
	var result: Variant = ClassDB.instantiate(result_class)
	if query == null or result == null:
		return {"ok": false, "error": "could not allocate %s / %s." % [query_class, result_class]}
	var raw_query: Variant = d.get("query", {})
	if raw_query is Dictionary:
		for key in raw_query:
			var prop := str(key)
			if prop == "shape" or prop == "shape_rid" or prop == "exclude":
				return {
					"ok": false,
					"error": "'%s' is not accepted in 'query'; pass shape_type/shape_properties or exclude instead." % prop,
				}
			var prop_type := _class_property_type(query_class, prop)
			if prop_type == -1:
				return {"ok": false, "error": "unknown %s field '%s'." % [query_class, prop]}
			query.set(prop, Coerce.from_json(raw_query[key], prop_type))
	if family == "Shape":
		var shape_built := _build_shape(d)
		if not bool(shape_built.get("ok", false)):
			return shape_built
		query.set("shape", shape_built["shape"])
	var excluded: Array = []
	var exclude_paths: Variant = d.get("exclude", [])
	if exclude_paths is Array:
		for path in exclude_paths:
			var target := get_node_or_null(NodePath(str(path)))
			if target == null:
				return {"ok": false, "error": "exclude node not found at '%s'." % str(path)}
			if not (target is CollisionObject2D or target is CollisionObject3D):
				return {
					"ok": false,
					"error": "exclude target '%s' is %s, not a CollisionObject2D/3D." % [
						str(path), target.get_class(),
					],
				}
			excluded.append(target.get_rid())
	if not excluded.is_empty():
		query.set("exclude", excluded)
	var max_results := clampi(int(d.get("max_results", 32)), 1, 1024)
	if "max_intersections" in result:
		result.set("max_intersections", max_results)
	elif "max_collisions" in result:
		result.set("max_collisions", max_results)
	return {"ok": true, "query": query, "result": result}


## Instantiate the query shape from shape_type/shape_properties (JSON can carry
## a Shape resource directly).
func _build_shape(d: Dictionary) -> Dictionary:
	var shape_type := str(d.get("shape_type", ""))
	if shape_type.is_empty():
		return {"ok": false, "error": "shape queries require 'shape_type' (e.g. 'SphereShape3D')."}
	var shape: Variant = ClassDB.instantiate(shape_type)
	if shape == null:
		return {"ok": false, "error": "could not instantiate shape_type '%s'." % shape_type}
	if not (shape is Shape2D or shape is Shape3D):
		shape = null
		return {"ok": false, "error": "'%s' is not a Shape2D/Shape3D." % shape_type}
	var properties: Variant = d.get("shape_properties", {})
	if properties is Dictionary:
		for key in properties:
			var prop := str(key)
			var prop_type := _class_property_type(shape_type, prop)
			if prop_type == -1:
				return {"ok": false, "error": "unknown %s property '%s'." % [shape_type, prop]}
			shape.set(prop, Coerce.from_json(properties[key], prop_type))
	return {"ok": true, "shape": shape}


func _class_property_type(type_name: String, prop: String) -> int:
	for entry in ClassDB.class_get_property_list(type_name, true):
		if str((entry as Dictionary).get("name", "")) == prop:
			return int((entry as Dictionary).get("type", -1))
	return -1


## Serialize the typed result object method-by-method. Never sends a Godot
## object: a collider becomes {path, class}, a RID becomes its numeric id.
func _collect_space_query_results(method: String, result: Object, reply: Dictionary) -> void:
	match method:
		"intersect_ray":
			if not bool(reply["hit"]):
				return
			reply["count"] = 1
			reply["results"] = [_ray_hit(result)]
		"get_rest_info":
			if not bool(reply["hit"]):
				return
			reply["count"] = 1
			reply["results"] = [_rest_hit(result)]
		"intersect_point", "intersect_shape":
			var intersections := int(result.call("get_intersection_count"))
			reply["count"] = intersections
			var hits: Array = []
			for i in intersections:
				var hit := _collider_entry(result.call("get_collider", i))
				hit["collider_id"] = int(result.call("get_collider_id", i))
				hit["collider_rid"] = _rid_id(result.call("get_collider_rid", i))
				hit["shape"] = int(result.call("get_collider_shape", i))
				hits.append(hit)
			reply["results"] = hits
		"collide_shape":
			var collisions := int(result.call("get_collision_count"))
			reply["count"] = collisions
			var pairs: Array = []
			for i in collisions:
				pairs.append({
					"point_on_queried_shape": Coerce.to_json(
						result.call("get_point_on_queried_shape", i)
					),
					"point_on_colliding_shape": Coerce.to_json(
						result.call("get_point_on_colliding_shape", i)
					),
				})
			reply["results"] = pairs
		"cast_motion":
			reply["count"] = 1 if bool(reply["hit"]) else 0
			reply["safe_fraction"] = float(result.get("safe_fraction"))
			reply["unsafe_fraction"] = float(result.get("unsafe_fraction"))


func _ray_hit(result: Object) -> Dictionary:
	var hit := _collider_entry(result.get("collider"))
	hit["collider_id"] = int(result.get("collider_id"))
	hit["collider_rid"] = _rid_id(result.get("collider_rid"))
	hit["shape"] = int(result.get("collider_shape"))
	hit["position"] = Coerce.to_json(result.get("position"))
	hit["normal"] = Coerce.to_json(result.get("normal"))
	hit["face_index"] = (
		int(result.get("collider_face_index")) if "collider_face_index" in result else -1
	)
	return hit


func _rest_hit(result: Object) -> Dictionary:
	var collider_id := int(result.get("collider_id"))
	var collider: Variant = instance_from_id(collider_id) if collider_id != 0 else null
	var hit := _collider_entry(collider)
	hit["collider_id"] = collider_id
	hit["collider_rid"] = _rid_id(result.get("collider_rid"))
	hit["shape"] = int(result.get("collider_shape"))
	hit["position"] = Coerce.to_json(result.get("point"))
	hit["normal"] = Coerce.to_json(result.get("normal"))
	hit["collider_velocity"] = Coerce.to_json(result.get("collider_velocity"))
	return hit


func _collider_entry(value: Variant) -> Dictionary:
	var entry := {"collider_path": "", "collider_class": ""}
	if value == null:
		return entry
	if value is Node:
		entry["collider_path"] = String(value.get_path())
	entry["collider_class"] = value.get_class()
	return entry


func _rid_id(value: Variant) -> int:
	if value != null and typeof(value) == TYPE_RID:
		return int(value.get_id())
	return 0


func _start_monitor(d: Dictionary) -> void:
	_monitor_target = NodePath(str(d.get("node_path", "")))
	_monitor_property = str(d.get("property", ""))
	_monitor_samples = []
	_monitor_error = ""
	_monitor_last_value = null
	_monitor_last_queued_frame = -1
	_monitor_sampling_usec = 0
	_monitor_dropped_duplicates = 0
	# #536: dedup defaults on; epsilon clamps to a sane positive range.
	_monitor_on_change_only = bool(d.get("on_change_only", true))
	_monitor_epsilon = clampf(float(d.get("epsilon", 0.0001)), 0.0, 1.0e9)
	var count := clampi(int(d.get("samples", 30)), 1, _MONITOR_MAX_SAMPLES)
	_monitor_requested = count
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
		# #536 honesty stats: the capture ran `requested` frames; `dropped_duplicates`
		# says how many unchanged readings were collapsed, and `sampling_usec` is the
		# cumulative probe-side sampling time (the profiling surface measures the win).
		"requested": _monitor_requested,
		"dropped_duplicates": _monitor_dropped_duplicates,
		"sampling_usec": _monitor_sampling_usec,
		"on_change_only": _monitor_on_change_only,
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


# --- input recording (issue #68) -------------------------------------------

const _RECORD_CAP := 2000  # bound the buffer so a long recording can't grow unbounded

var _recording := false
var _record_motion := false
var _recorded: Array = []


## Capture input the running game receives (in the play_input_sequence event format) so it
## can be replayed for regression. Runs only while recording is active.
func _input(event: InputEvent) -> void:
	if not _recording:
		return
	var rec := _serialize_event(event)
	if not rec.is_empty() and _recorded.size() < _RECORD_CAP:
		_recorded.append(rec)


func _record_start(d: Dictionary) -> void:
	_record_motion = bool(d.get("include_motion", false))
	_recorded = []
	_recording = true


func _record_stop() -> void:
	_recording = false
	EngineDebugger.send_message("godot_mcp:recorded_input", [{"events": _recorded}])


## Serialize an InputEvent into the {type, …} shape play_input_sequence replays, or {} to
## skip (unhandled event kinds, motion when not requested, unmapped buttons/keys).
func _serialize_event(event: InputEvent) -> Dictionary:
	if event is InputEventKey:
		var key := OS.get_keycode_string(event.keycode)
		if key.is_empty():
			return {}
		return {
			"type": "key", "key": key, "pressed": event.pressed,
			"shift": event.shift_pressed, "ctrl": event.ctrl_pressed,
			"alt": event.alt_pressed, "meta": event.meta_pressed,
		}
	if event is InputEventMouseButton:
		var button := _button_name(event.button_index)
		if button.is_empty():
			return {}
		return {
			"type": "mouse", "x": event.position.x, "y": event.position.y,
			"button": button, "pressed": event.pressed,
		}
	if event is InputEventMouseMotion:
		if not _record_motion:
			return {}
		return {
			"type": "mouse", "x": event.position.x, "y": event.position.y,
			"relative_x": event.relative.x, "relative_y": event.relative.y,
		}
	return {}


## Reverse of _MOUSE_BUTTONS: button index → name, or "" if not a recognized button.
func _button_name(index: int) -> String:
	for name in _MOUSE_BUTTONS:
		if _MOUSE_BUTTONS[name] == index:
			return name
	return ""


# --- game output capture (issue #534) ----------------------------------------

## The bounded output ring: entries {seq, kind, text, time_ms}. kind is
## "stdout" (print + printerr-style stderr lines), "error" (push_error /
## script errors / engine errors), or "warning" (push_warning / engine
## warnings). Bounded per the honesty rules — eviction is counted (`dropped`),
## never silent.
const MAX_OUTPUT := 500

## The ring + the running sequence cursor + the eviction counter. The Logger
## callback can fire from ANY thread (Godot logging contract), so all access
## is mutex-guarded.
var _output_lock: Mutex = Mutex.new()
var _output_ring: Array = []
var _output_seq := 0
var _output_dropped := 0
# #648: typed Object, not Logger — a `: Logger` annotation would fail to parse on
# the 4.4 floor (Logger is 4.5+). Null on 4.4 / when output capture is unavailable.
var _output_logger: Object = null


## Register the output logger in _ready (EngineDebugger-active gate lives in
## _ready; the logger is registered alongside it so captures start as early
## as the probe itself).
##
## #648/#738: `Logger` + `OS.add_logger` are Godot 4.5+. A Logger subclass cannot
## live in a `.gd` file: the editor parses every script in the project (even
## without a `class_name`), so extending Logger would break the 4.4/4.6 floor at
## editor load. Compile the subclass from this string instead — only when the
## 4.5+ API exists — so the 4.4 editor never parses it. Output capture degrades
## to an empty ring on 4.4; every other probe feature works.
const _LOGGER_SOURCE := """
extends Logger

var _sink: Callable


func _init(sink: Callable) -> void:
	_sink = sink


func _log_message(message: String, error: bool) -> void:
	_sink.call(message, "error" if error else "stdout")


func _log_error(
	function: String, file: String, line: int, code: String, rationale: String,
	_editor_notify: bool, error_type: int, _script_backtraces: Array
) -> void:
	var kind := "error"
	if error_type == Logger.ERROR_TYPE_WARNING:
		kind = "warning"
	# `rationale` carries the human text for push_error/push_warning/script errors;
	# `code` is the engine-side message. Prefer whichever is present.
	var text := rationale
	if text.is_empty():
		text = code
	if text.is_empty():
		text = "%s @ %s:%d" % [function, file, line]
	_sink.call(text, kind)
"""


func _register_output_logger() -> void:
	if not OS.has_method("add_logger"):
		return
	var logger_script := GDScript.new()
	logger_script.source_code = _LOGGER_SOURCE
	if logger_script.reload() != OK:
		return
	_output_logger = logger_script.new(_on_output_line)
	OS.call("add_logger", _output_logger)


## Logger sink (any thread): append {seq, kind, text, time_ms} into the ring,
## evicting the oldest entry (counted) beyond MAX_OUTPUT.
func _on_output_line(text: String, kind: String) -> void:
	_output_lock.lock()
	_output_seq += 1
	_output_ring.append({
		"seq": _output_seq,
		"kind": kind,
		"text": text,
		"time_ms": float(Time.get_ticks_msec()),
	})
	if _output_ring.size() > MAX_OUTPUT:
		_output_ring.pop_front()
		_output_dropped += 1
	_output_lock.unlock()


## Snapshot the ring for the editor (called from _capture → get_output).
## Returns {entries, next_seq, total, dropped}; `total` is the count of
## entries ever captured so the editor can detect eviction (entries <
## total - dropped is impossible; dropped is the honest eviction count).
func _output_snapshot() -> Dictionary:
	_output_lock.lock()
	var entries := _output_ring.duplicate(true)
	var next_seq := _output_seq
	var dropped := _output_dropped
	_output_lock.unlock()
	return {
		"entries": entries,
		"next_seq": next_seq,
		"total": next_seq,
		"dropped": dropped,
	}
