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


func _has_capture(capture: String) -> bool:
	return capture == CAPTURE_PREFIX


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
