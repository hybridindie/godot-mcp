@tool
class_name MCPDebuggerHandlers
extends RefCounted
## Domain handler: debugger breakpoint control (issue #110, Tier 1).
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_set_breakpoint"] = _cmd_set_breakpoint
	handlers["cmd_remove_breakpoint"] = _cmd_remove_breakpoint
	handlers["cmd_clear_breakpoints"] = _cmd_clear_breakpoints
	handlers["cmd_force_break"] = _cmd_force_break
	# Read-only break-state check the server polls after force_break (#411) —
	# the break lands a frame or two after the probe services the flag.
	handlers["cmd_get_debug_break_state"] = _cmd_get_debug_break_state
	# Tier 2: step control via EditorDebuggerSession.send_message
	handlers["cmd_step_into"] = _cmd_step
	handlers["cmd_step_over"] = _cmd_step
	handlers["cmd_step_out"] = _cmd_step
	handlers["cmd_continue_execution"] = _cmd_continue
	# Tier 2: stack / eval
	handlers["cmd_get_stack_frames"] = _cmd_get_stack_frames
	handlers["cmd_evaluate_expression"] = _cmd_evaluate_expression
	handlers["cmd_get_frame_variables"] = _cmd_get_frame_variables



# -- handlers ----------------------------------------------------------------

func _cmd_set_breakpoint(params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard
	var path := str(params.get("path", ""))
	var line := int(params.get("line", 0))
	if path.is_empty() or line <= 0:
		return _router._fail("VALIDATION_ERROR", "'path' and 'line' are required and line must be > 0.")

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	session.set_breakpoint(path, line, true)
	debugger.track_breakpoint(path, line, true)
	return _router._ok({"breakpoint_set": true, "path": path, "line": line})


func _cmd_remove_breakpoint(params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard
	var path := str(params.get("path", ""))
	var line := int(params.get("line", 0))
	if path.is_empty() or line <= 0:
		return _router._fail("VALIDATION_ERROR", "'path' and 'line' are required and line must be > 0.")

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	session.set_breakpoint(path, line, false)
	debugger.track_breakpoint(path, line, false)
	return _router._ok({"breakpoint_removed": true, "path": path, "line": line})


func _cmd_clear_breakpoints(_params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var debugger := _router._debugger as MCPDebugger
	# Clear on the game side via the probe when available.
	if debugger.is_connected_to_probe():
		debugger.send_to_probe("godot_mcp:clear_breakpoints", [])
	# Also clear any individually tracked breakpoints in the current session.
	var tracked: Array = debugger.get_tracked_breakpoints()
	for bp in tracked:
		var bp_path: String = str(bp.get("path", ""))
		var bp_line: int = int(bp.get("line", 0))
		if not bp_path.is_empty() and bp_line > 0:
			var session := debugger.get_session(debugger.get_session_id())
			session.set_breakpoint(bp_path, bp_line, false)
	debugger.clear_tracked_breakpoints()
	return _router._ok({"breakpoints_cleared": true})


## Read-only: is the debug session currently in the break loop? Polled by the
## server after force_break so the tool can report whether the game actually
## paused (#411).
func _cmd_get_debug_break_state(_params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard
	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	var breaked: bool = session.is_breaked()
	return _router._ok({"breaked": breaked})



func _cmd_force_break(_params: Dictionary) -> Dictionary:
	var guard := _router._require_live_probe()
	if not guard["ok"]:
		return guard
	_router._debugger.send_to_probe("godot_mcp:force_break", [])
	# Non-blocking (the editor thread must not sleep): the probe services the
	# force_break flag on its next frame, so the server polls
	# cmd_get_debug_break_state for the break state (#411). Report the current
	# state so the tool result is meaningful even without polling.
	var breaked := false
	var session = _router._debugger.get_session(_router._debugger.get_session_id())
	if session != null and session.is_breaked():
		breaked = true
	return _router._ok({
		"force_break_sent": true,
		"breaked": breaked,
	})

# Tier 2: step control via EditorDebuggerSession.send_message ----------------

## Maps the MCP tool name (from the command string) to the Godot debugger protocol
## message string sent to the session.
const _STEP_COMMANDS: Dictionary = {
	"cmd_step_into": "step",
	"cmd_step_over": "next",
	"cmd_step_out": "out",
}


func _cmd_step(params: Dictionary, command: String) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if not session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is not paused. Set a breakpoint or force_break first.",
			"break_state",
		)

	var msg: String = _STEP_COMMANDS.get(command, "")
	if msg.is_empty():
		return _router._fail("INTERNAL_ERROR", "Unknown step command '%s'." % command)

	session.send_message(msg, [])
	return _router._ok({"stepped": true})


func _cmd_continue(_params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if not session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is not paused. Set a breakpoint or force_break first.",
			"break_state",
		)

	session.send_message("continue", [])
	return _router._ok({"running": true})


# Tier 2: stack / eval ------------------------------------------------------

func _cmd_get_stack_frames(params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if not session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is not paused. Set a breakpoint or force_break first.",
			"break_state",
		)

	# #671: request-scoped — serve the cached stack only when it answers THIS
	# request_id; else dispatch once and report pending (the server polls).
	var request_id := str(params.get("request_id", ""))
	var cached: Variant = debugger.get_cached_stack_frames()
	if cached is Dictionary and str((cached as Dictionary).get("request_id", "")) == request_id:
		return _router._ok({"ready": true, "frames": (cached as Dictionary).get("frames", [])})
	if debugger.get_stack_request() != request_id:
		debugger.begin_stack_request(request_id)
		debugger.request_stack_frames()
	return _router._ok({
		"ready": false,
		"frames": [],
		"reason": "stack_pending",
		"hint": "No stack dump yet for this request; the game may still be delivering it (the server polls until it arrives).",
	})


func _cmd_evaluate_expression(params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var expression := str(params.get("expression", ""))
	if expression.is_empty():
		return _router._fail("VALIDATION_ERROR", "'expression' is required.")
	var frame := int(params.get("frame", 0))

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if not session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is not paused. Set a breakpoint or force_break first.",
			"break_state",
		)

	# #671: request-scoped — serve the cached value only when it answers THIS
	# request_id; else dispatch once and report pending (the server polls).
	var request_id := str(params.get("request_id", ""))
	var cached: Variant = debugger.get_cached_evaluation()
	if cached is Dictionary and str((cached as Dictionary).get("request_id", "")) == request_id:
		return _router._ok({
			"ready": true,
			"expression": expression,
			"value": (cached as Dictionary).get("value", null),
			"evaluated": true,
		})
	if debugger.get_evaluation_request() != request_id:
		debugger.begin_evaluation_request(request_id)
		debugger.request_evaluation(expression, frame)
	# value:null with evaluated:false means "no reply for this request yet" (#411).
	return _router._ok({
		"ready": false,
		"expression": expression,
		"value": null,
		"evaluated": false,
		"reason": "evaluation_pending",
	})


func _cmd_get_frame_variables(params: Dictionary) -> Dictionary:
	var guard := _router._require_debug_session()
	if not guard["ok"]:
		return guard

	var frame := int(params.get("frame", 0))

	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if not session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is not paused. Set a breakpoint or force_break first.",
			"break_state",
		)

	# #671: request-scoped — serve the accumulation only when it answers THIS
	# request_id; else dispatch once and report pending (the server polls).
	var request_id := str(params.get("request_id", ""))
	var cached: Variant = debugger.get_cached_frame_vars()
	if cached is Dictionary and str((cached as Dictionary).get("request_id", "")) == request_id:
		var d: Dictionary = cached as Dictionary
		return _router._ok({
			"ready": true,
			"frame": frame,
			"locals": d.get("locals", []),
			"members": d.get("members", []),
			"globals": d.get("globals", []),
		})
	if debugger.get_frame_vars_request() != request_id:
		debugger.begin_frame_vars_request(request_id)
		debugger.request_frame_variables(frame)
	return _router._ok({
		"ready": false,
		"frame": frame,
		"locals": [],
		"members": [],
		"globals": [],
		"reason": "frame_vars_pending",
	})
