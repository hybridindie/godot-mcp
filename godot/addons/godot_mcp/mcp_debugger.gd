@tool
class_name MCPDebugger
extends EditorDebuggerPlugin
## Captures the ``godot_mcp:`` debugger channel from a running game (issue #66).
##
## A custom EditorDebuggerPlugin only receives messages with its own prefix, so the
## running game must include the godot-mcp runtime probe autoload
## (``mcp_runtime_probe.gd``), which registers an ``EngineDebugger`` capture and answers
## our queries. Replies are **cached** here so the synchronous WS command handlers can
## read live runtime state without making the bridge async (poll-and-cache).

const CAPTURE_PREFIX := "godot_mcp"

var _session_id: int = -1
var _session_active: bool = false
var _probe_ready: bool = false
var _scene_tree: Variant = null  # last godot_mcp:scene_tree payload (Dictionary) or null
var _input_acks: int = 0  # count of synthesized inputs the game has acknowledged (#36)
var _property_samples: Variant = null  # last godot_mcp:property_samples payload (#35)
var _ui_elements: Variant = null  # last godot_mcp:ui_elements payload (#35)
var _ui_pending := "__none__"  # request_id of the in-flight find_ui request (#35)
var _recorded_input: Variant = null  # last godot_mcp:recorded_input payload (#68)
var _performance: Variant = null  # last godot_mcp:performance payload (#38)
var _breakpoints: Array = []  # tracked breakpoints for issue #110
var _stack_frames: Variant = null  # last stack_dump payload (Tier 2)
var _evaluation_result: Variant = null  # last evaluation_return payload (Tier 2)
var _frame_vars: Variant = null  # last accumulated frame vars (Tier 2)
var _frame_vars_expected: int = 0  # count from stack_frame_vars (Tier 2)
var _frame_vars_locals: Array = []
var _frame_vars_members: Array = []
var _frame_vars_globals: Array = []


## Debugger protocol capture names we claim so _capture receives raw messages.
const _DEBUGGER_CAPTURES := ["stack_dump", "evaluation_return", "stack_frame_vars", "stack_frame_var"]


func _has_capture(capture: String) -> bool:
	return capture == CAPTURE_PREFIX or capture in _DEBUGGER_CAPTURES


func _capture(message: String, data: Array, session_id: int) -> bool:
	match message:
		"godot_mcp:ready":
			_probe_ready = true
			_session_id = session_id
			request_scene_tree()  # warm the cache as soon as the probe announces itself
			return true
		"godot_mcp:pong":
			return true
		"godot_mcp:scene_tree":
			_scene_tree = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:input_ack":
			_input_acks += 1
			return true
		"godot_mcp:property_samples":
			_property_samples = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:ui_elements":
			_ui_elements = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:recorded_input":
			_recorded_input = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:performance":
			_performance = data[0] if not data.is_empty() else null
			return true
		# Tier 2 debugger: raw Godot debugger protocol replies (issue #110)
		"stack_dump":
			_stack_frames = data[0] if not data.is_empty() else null
			return true
		"evaluation_return":
			_evaluation_result = data[0] if not data.is_empty() else null
			return true
		"stack_frame_vars":
			# The count message tells us how many variables to expect; reset accumulators.
			_frame_vars_expected = data[0] if not data.is_empty() else 0
			_frame_vars_locals = []
			_frame_vars_members = []
			_frame_vars_globals = []
			_frame_vars = null
			return true
		"stack_frame_var":
			# Accumulate a single variable: [type(0=local,1=member,2=global), name, value]
			if data.size() >= 3:
				var vtype: int = int(data[0])
				var entry := {"name": str(data[1]), "value": data[2]}
				match vtype:
					0:
						_frame_vars_locals.append(entry)
					1:
						_frame_vars_members.append(entry)
					2:
						_frame_vars_globals.append(entry)
				# When the expected count is reached, build the final dict.
				var total := _frame_vars_locals.size() + _frame_vars_members.size() + _frame_vars_globals.size()
				if total >= _frame_vars_expected:
					_frame_vars = {
						"locals": _frame_vars_locals.duplicate(),
						"members": _frame_vars_members.duplicate(),
						"globals": _frame_vars_globals.duplicate(),
					}
			return true
	return false


func _setup_session(session_id: int) -> void:
	_session_id = session_id
	var session := get_session(session_id)
	session.started.connect(func() -> void: _on_started(session_id))
	session.stopped.connect(_on_stopped)


func _on_started(session_id: int) -> void:
	_session_active = true
	_session_id = session_id


func _on_stopped() -> void:
	_session_active = false
	_probe_ready = false
	_scene_tree = null
	_input_acks = 0
	_property_samples = null
	_ui_elements = null
	_ui_pending = "__none__"
	_recorded_input = null
	_performance = null
	_stack_frames = null
	_evaluation_result = null
	_frame_vars = null
	_frame_vars_expected = 0
	_frame_vars_locals = []
	_frame_vars_members = []
	_frame_vars_globals = []


## Ask the running game's probe to (re)send the scene tree. The reply lands in the cache
## on a later frame via _capture; callers read get_cached_scene_tree().
func request_scene_tree() -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message("godot_mcp:get_scene_tree", [])


## True once a play session is live AND its probe has announced itself.
func is_connected_to_probe() -> bool:
	return _session_active and _probe_ready


func get_cached_scene_tree() -> Variant:
	return _scene_tree


## Send a godot_mcp:* message to the running game's probe (fire-and-forget).
func send_to_probe(message: String, data: Array = []) -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message(message, data)


func get_input_acks() -> int:
	return _input_acks


func get_property_samples() -> Variant:
	return _property_samples


## Drop the cached samples so a fresh monitor_property doesn't read the prior capture
## (the next get_property_samples reports ready=false until the new series arrives).
func clear_property_samples() -> void:
	_property_samples = null


func get_ui_elements() -> Variant:
	return _ui_elements


## request_id of the in-flight find_ui request (so the router dispatches a scan only once
## per invocation rather than re-scanning on every poll).
func get_pending_ui_request() -> String:
	return _ui_pending


## Mark a new find_ui request as in-flight and drop any prior (stale) result.
func begin_ui_request(request_id: String) -> void:
	_ui_pending = request_id
	_ui_elements = null


func get_recorded_input() -> Variant:
	return _recorded_input


## Drop the cached recording so stop_recording reads the new capture, not a prior one.
func clear_recorded_input() -> void:
	_recorded_input = null


func get_performance() -> Variant:
	return _performance


## Cache accessors for Tier 2 debugger tools (step, stack, eval).

func get_cached_stack_frames() -> Variant:
	return _stack_frames


func get_cached_evaluation() -> Variant:
	return _evaluation_result


func get_cached_frame_vars() -> Variant:
	return _frame_vars


## Ask the editor debugger for the current call stack. Reply lands in
## _stack_frames via _capture("stack_dump", data).
func request_stack_frames() -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message("get_stack_dump", [])


## Ask the editor debugger to evaluate ``expression`` at ``frame`` (0 is top).
## Reply lands in _evaluation_result via _capture("evaluation_return", data).
func request_evaluation(expression: String, frame: int = 0) -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message("evaluate", [expression, frame])


## Ask the editor debugger for locals / members / globals at ``frame`` (0 is top).
## Reply lands in _frame_vars via _capture("stack_frame_vars", data).
func request_frame_variables(frame: int = 0) -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message("get_stack_frame_vars", [frame])


## Return the current session ID so handlers can call get_session().
func get_session_id() -> int:
	return _session_id


## Track a breakpoint in our local list (issue #110).
func track_breakpoint(path: String, line: int, enabled: bool) -> void:
	# Remove any existing entry for this exact path+line.
	for i in range(_breakpoints.size() - 1, -1, -1):
		var bp: Dictionary = _breakpoints[i]
		if str(bp.get("path", "")) == path and int(bp.get("line", 0)) == line:
			_breakpoints.remove_at(i)
	if enabled:
		_breakpoints.append({"path": path, "line": line})


## Return all currently tracked breakpoints.
func get_tracked_breakpoints() -> Array:
	return _breakpoints.duplicate()


## Clear the tracked breakpoint list.
func clear_tracked_breakpoints() -> void:
	_breakpoints.clear()
