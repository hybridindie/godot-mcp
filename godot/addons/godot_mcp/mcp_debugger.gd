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
# #454: the engine keeps every debugger tab ever created and caps *active*
# sessions (4 — EditorDebuggerNode), printing "Max client limits reached" only
# from its DAP/LSP servers when those caps hit. A session leak is otherwise
# invisible, so the plugin enforces a one-active-session contract itself: a new
# session drops the previous session's signal wiring (no accumulating lambdas
# across play/stop cycles) and a diagnostic names multiple live sessions.
var _previous_session_id: int = -1
# The specific callables THIS plugin connected on the current session (round-2
# review: disconnect only ours — the editor's own debugger infrastructure also
# listens on these signals, and a blanket disconnect breaks its tab bookkeeping).
var _owned_connections: Array = []
var _scene_tree: Variant = null  # last godot_mcp:scene_tree payload (Dictionary) or null
var _input_acks: int = 0  # count of synthesized inputs the game has acknowledged (#36)
var _property_samples: Variant = null  # last godot_mcp:property_samples payload (#35)
var _read_property: Variant = null  # last godot_mcp:read_property one-shot reply (#571)
var _read_property_pending := "__none__"  # request_id of the in-flight one-shot read (#571)
var _ui_elements: Variant = null  # last godot_mcp:ui_elements payload (#35)
var _ui_pending := "__none__"  # request_id of the in-flight find_ui request (#35)
var _recorded_input: Variant = null  # last godot_mcp:recorded_input payload (#68)
var _performance: Variant = null  # last godot_mcp:performance payload (#38)
var _game_frame: Variant = null  # last godot_mcp:game_frame payload (#446)
var _frame_request_id := "__none__"  # request_id of the in-flight game frame capture (#446)
var _game_output: Variant = null  # last godot_mcp:game_output payload (#534)
var _breakpoints: Array = []  # tracked breakpoints for issue #110
var _evaluation_result: Variant = null  # last godot_mcp:evaluation payload (#677)
# #670/#677: request ids for the probe-backed reads, so a handler serves the reply
# for THIS request — never the previous call's cached value. The probe echoes the id.
var _scene_tree_request := "__none__"
var _performance_request := "__none__"
var _evaluation_request := "__none__"


func _has_capture(capture: String) -> bool:
	return capture == CAPTURE_PREFIX


func _capture(message: String, data: Array, session_id: int) -> bool:
	match message:
		"godot_mcp:ready":
			_probe_ready = true
			_session_id = session_id
			return true
		"godot_mcp:pong":
			return true
		"godot_mcp:scene_tree":
			# #670: the probe echoes the request_id; store only when it matches the
			# in-flight request (a legacy probe sends no id — tag it with the pending
			# id so the stored shape is uniform).
			var tree_payload: Variant = data[0] if not data.is_empty() else null
			if tree_payload is Dictionary and (tree_payload as Dictionary).has("request_id"):
				if str((tree_payload as Dictionary).get("request_id", "")) == _scene_tree_request:
					_scene_tree = tree_payload
			else:
				_scene_tree = {"request_id": _scene_tree_request, "tree": tree_payload}
			return true
		"godot_mcp:input_ack":
			_input_acks += 1
			return true
		"godot_mcp:property_samples":
			_property_samples = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:read_property":
			# Qodo review (#575): only store the reply when it matches the pending
			# request — a delayed reply to an older request must not serve as the
			# current one's result (the one-shot value is returned directly).
			var reply: Variant = data[0] if not data.is_empty() else null
			if reply is Dictionary:
				var pending := _read_property_pending
				if pending != "__none__" and str((reply as Dictionary).get("request_id", "")) == pending:
					_read_property = reply
			return true
		"godot_mcp:ui_elements":
			# #577 (Qodo review of #575): same stale-reply gate as read_property —
			# store the scan reply only when its request_id matches the pending
			# scan, so a delayed reply to an older request can't be served to a
			# new poll (wrong rects to click).
			var scan: Variant = data[0] if not data.is_empty() else null
			if scan is Dictionary:
				var pending_scan := _ui_pending
				if pending_scan != "__none__" and str((scan as Dictionary).get("request_id", "")) == pending_scan:
					_ui_elements = scan
			return true
		"godot_mcp:recorded_input":
			_recorded_input = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:performance":
			# #670: same request-id gate as scene_tree.
			var perf_payload: Variant = data[0] if not data.is_empty() else null
			if perf_payload is Dictionary and (perf_payload as Dictionary).has("request_id"):
				if str((perf_payload as Dictionary).get("request_id", "")) == _performance_request:
					_performance = perf_payload
			else:
				_performance = {"request_id": _performance_request, "monitors": perf_payload}
			return true
		"godot_mcp:game_frame":
			_game_frame = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:game_output":
			_game_output = data[0] if not data.is_empty() else null
			return true
		"godot_mcp:evaluation":
			# #677: the probe evaluates in-game and echoes the request_id; store
			# only when it matches the in-flight evaluation request.
			var ev: Variant = data[0] if not data.is_empty() else null
			if ev is Dictionary and str((ev as Dictionary).get("request_id", "")) == _evaluation_request:
				_evaluation_result = ev
			return true
	return false


func _setup_session(session_id: int) -> void:
	# #454: one-active-session contract. When the editor hands us a new session,
	# detach the previous session's signal wiring (each play/stop cycle otherwise
	# leaves a connected lambda pair behind) and adopt the new one immediately —
	# its ``started`` signal may never fire (orphaned-session recovery), so the
	# new session is also reset+adopted right here, not just on _on_started.
	if _session_id >= 0 and _session_id != session_id:
		_previous_session_id = _session_id
		_detach_previous_session(session_id)
	_session_id = session_id
	var session := get_session(session_id)
	if session == null:
		return
	var on_start := func() -> void: _on_started(session_id)
	session.started.connect(on_start)
	session.stopped.connect(_on_stopped)
	# Track exactly what this plugin connected (round-2 review: the detach must
	# only remove ours — the editor's own consumers share these signals).
	_owned_connections = [
		{"signal": session.started, "callable": on_start},
		{"signal": session.stopped, "callable": _on_stopped},
	]
	# A session arriving while another is still live is the pre-condition for
	# the engine's session cap — surface it instead of staying silent (#454).
	var live: Array = []
	for s in get_sessions():
		if s.is_active():
			live.append(s.id)
	if live.size() > 1:
		print(("[MCPDebugger] multiple live debugger sessions: %s — "
			+ "engine caps concurrent sessions; if the new game connects but the probe never "
			+ "announces, check the editor log for \"max client limits reached\" "
			+ "(DAP/LSP client caps) and restart the editor if sessions are exhausted.")
			% str(live))


func _on_started(session_id: int) -> void:
	_session_active = true
	_session_id = session_id


## Drop the previous session's signal wiring (#454). The engine keeps every
## debugger tab; without this, each play/stop cycle leaves one more connected
## lambda pair — invisible until a cap bites. Only the plugin's OWN callables are
## disconnected (tracked in _owned_connections): the editor's internal debugger
## consumers also listen on these signals, and a blanket disconnect would break
## their tab bookkeeping (Qodo #455 review).
func _detach_previous_session(_new_session_id: int) -> void:
	var previous := get_session(_previous_session_id)
	if previous == null:
		return
	for owned in _owned_connections:
		var signal_ref: Signal = owned["signal"]
		var callable: Callable = owned["callable"]
		if signal_ref.is_connected(callable):
			signal_ref.disconnect(callable)
	_owned_connections.clear()


func _on_stopped() -> void:
	_session_active = false
	_probe_ready = false
	_scene_tree = null
	_scene_tree_request = "__none__"
	_input_acks = 0
	_property_samples = null
	_read_property = null
	_read_property_pending = "__none__"
	_ui_elements = null
	_ui_pending = "__none__"
	_recorded_input = null
	_performance = null
	_performance_request = "__none__"
	_game_frame = null
	_frame_request_id = "__none__"
	_evaluation_result = null
	_evaluation_request = "__none__"


## Release the plugin's own references so it can be freed when the editor exits.
##
## _setup_session() stores Callables bound to ``self`` and connects them to the
## session, so the plugin keeps a reference to itself — and the session keeps one
## too — until both sides let go; remove_debugger_plugin() only unregisters the
## plugin and does not drop them. RefCounted cycles are never freed automatically
## (see the RefCounted class reference), which left this plugin and
## mcp_debugger.gd alive as leaked instances at editor exit. Called from the
## plugin's _exit_tree() before remove_debugger_plugin().
func dispose() -> void:
	for owned in _owned_connections:
		var signal_ref: Signal = owned["signal"]
		var callable: Callable = owned["callable"]
		if is_instance_valid(signal_ref.get_object()) and signal_ref.is_connected(callable):
			signal_ref.disconnect(callable)
	_owned_connections.clear()
	_previous_session_id = -1
	_session_id = -1
	_session_active = false
	_probe_ready = false


## Ask the running game's probe to (re)send the scene tree for ``request_id``. The
## reply lands in the cache on a later frame via _capture; callers read
## get_cached_scene_tree() and serve it only when its request_id matches.
func request_scene_tree(request_id: String = "__none__") -> void:
	if not _session_active or _session_id < 0:
		return
	var session := get_session(_session_id)
	if session != null and session.is_active():
		session.send_message("godot_mcp:get_scene_tree", [{"request_id": request_id}])


## True once a play session is live AND its probe has announced itself.
func is_connected_to_probe() -> bool:
	return _session_active and _probe_ready


func get_cached_scene_tree() -> Variant:
	return _scene_tree


## #670: request_id of the in-flight scene-tree read (so repeated polls don't
## re-dispatch and a stale reply can't be served to a new request).
func get_scene_tree_request() -> String:
	return _scene_tree_request


## Mark a new scene-tree request as in-flight and drop any prior (stale) tree.
func begin_scene_tree_request(request_id: String) -> void:
	_scene_tree_request = request_id
	_scene_tree = null


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


# #571 one-shot read cache (mirrors the find_ui request_id pattern).
func get_read_property() -> Variant:
	return _read_property


## request_id of the in-flight one-shot read (so repeated polls don't re-dispatch
## and a completed read isn't confused with a prior request's stale reply).
func get_pending_read_request() -> String:
	return _read_property_pending


## Mark a new one-shot read as in-flight and drop any prior (stale) reply.
func begin_read_request(request_id: String) -> void:
	_read_property_pending = request_id
	_read_property = null


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


## #670: request_id of the in-flight performance read.
func get_performance_request() -> String:
	return _performance_request


## Mark a new performance read as in-flight and drop any prior (stale) snapshot.
func begin_performance_request(request_id: String) -> void:
	_performance_request = request_id
	_performance = null


## Ask the running game's probe for a fresh Performance snapshot for ``request_id``
## (the reply echoes the id; _capture gates the cache on it).
func request_performance(request_id: String) -> void:
	send_to_probe("godot_mcp:get_performance", [{"request_id": request_id}])


## request_id of the in-flight game frame capture (so the router dispatches a
## grab only once per invocation, mirroring the find_ui request pattern).
func get_pending_frame_request() -> String:
	return _frame_request_id


## Mark a new game-frame capture as in-flight and drop any prior (stale) frame.
func begin_frame_request(request_id: String) -> void:
	_frame_request_id = request_id
	_game_frame = null


func get_game_frame() -> Variant:
	return _game_frame


## Issue #534: the probe's game-output ring (poll-and-cache — the editor pulls
## on demand via the godot_mcp:get_output query; nothing pushes unsolicited).
func get_game_output() -> Variant:
	return _game_output


## Cache accessor for the in-game expression evaluation (issue #677).

func get_cached_evaluation() -> Variant:
	return _evaluation_result


## #677: request_id of the in-flight evaluation.
func get_evaluation_request() -> String:
	return _evaluation_request


## Mark a new evaluation in-flight and drop the prior (stale) reply.
func begin_evaluation_request(request_id: String) -> void:
	_evaluation_request = request_id
	_evaluation_result = null


## Ask the running game's probe to evaluate ``expression`` for ``request_id``.
## #677: evaluation runs in-game via Expression (the editor debugger's paused-frame
## eval protocol is not exposed to editor debugger plugins on 4.7). The reply lands
## in _evaluation_result via _capture("godot_mcp:evaluation", data).
func request_evaluation(request_id: String, expression: String) -> void:
	send_to_probe("godot_mcp:evaluate", [{"request_id": request_id, "expression": expression}])


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
