@tool
class_name MCPGuards
extends RefCounted
## The one home for the runtime probe / debug-session precondition guards (#527).
##
## Three drifted flavors used to live in command_router.gd
## (_require_debug_session / _require_live_probe) and inline in
## handlers/runtime_session.gd (_cmd_get_game_scene_tree, which was the only
## handler surfacing the #454 probe-never-connected diagnostic). This module
## consolidates them so:
##   - every probe-gated handler returns the SAME structured envelopes;
##   - the #454 "max client limits reached" diagnostic ships from every
##     probe-never-connected failure, not just get_game_scene_tree;
##   - the #443 break gate (input while frozen at a break) lives here too.
##
## Handlers receive the router so _fail/_ok envelope builders stay centralized.
## See .opencode/rules/error-handling.md; safety/preconditions are owned by the
## MCP server — these are the local guards needed to return a structured error
## instead of crashing.

var _router: MCPCommandRouter
## Editor-state oracle: returns ``EditorInterface.is_playing_scene()`` by
## default. Injectable so the headless smoke (godot/tests/guards_smoke.gd,
## where the EditorInterface singleton exists but play APIs are unavailable)
## can exercise every guard branch deterministically.
var _is_playing: Callable


func _init(router: MCPCommandRouter) -> void:
	_router = router
	_is_playing = func() -> bool: return EditorInterface.is_playing_scene()


## Test seam: override the play-session oracle (guards_smoke.gd). Production
## never calls this.
func set_play_session_oracle(oracle: Callable) -> void:
	_is_playing = oracle


# -- composable guards ---------------------------------------------------------

## A play session must be live (the game is running from the editor).
func require_play_session() -> Dictionary:
	if not _is_playing.call():
		return _router._fail(
			"PRECONDITION_FAILED", "No play session. Run play_scene first.", "play_session"
		)
	return {"ok": true}


## Guard for breakpoint operations: a play session must be live with a valid
## debug session (the game attached to the editor debugger).
func require_debug_session() -> Dictionary:
	var base := require_play_session()
	if not base["ok"]:
		return base
	if _router._debugger == null:
		return _router._fail("INTERNAL_ERROR", "Debugger plugin is unavailable.")
	if _router._debugger.get_session_id() < 0:
		return _router._fail(
			"PRECONDITION_FAILED",
			"No active debug session. The game may not have connected to the editor debugger yet.",
			"play_session",
		)
	return {"ok": true}


## Guard for live-probe consumers: a play session must be live AND the
## godot_mcp runtime probe connected. The probe-never-connected case carries
## the full #454 diagnostic (autoload reminder + the play/stop-cycle session-cap
## recovery hint), so EVERY gated handler — not just get_game_scene_tree —
## diagnoses a missing/unattached probe for the agent.
func require_live_probe() -> Dictionary:
	var base := require_play_session()
	if not base["ok"]:
		return base
	if _router._debugger == null:
		return _router._fail("INTERNAL_ERROR", "Debugger plugin is unavailable.")
	if not _router._debugger.is_connected_to_probe():
		return _router._fail(
			"PRECONDITION_FAILED",
			probe_never_connected_hint(),
			"runtime_probe",
		)
	return {"ok": true}


## Guard for input injection (#443 break gate): a live probe AND the game not
## frozen at a debugger break — injected input while paused can never be
## processed, so it must be refused (an acked-but-frozen sent:true reads as a
## gameplay bug — the #411 trap). continue_execution or unpause clears it.
func require_unpaused_live_probe() -> Dictionary:
	var guard := require_live_probe()
	if not guard["ok"]:
		return guard
	var debugger := _router._debugger as MCPDebugger
	var session := debugger.get_session(debugger.get_session_id())
	if session != null and session.is_breaked():
		return _router._fail(
			"PRECONDITION_FAILED",
			"The game is paused at a debugger break; injected input is frozen alongside the game. Call continue_execution or unpause before injecting input.",
			"game_not_breaked",
		)
	return {"ok": true}


## Whether the game is currently paused at a debugger break (the #411 tell an
## agent needs before trusting input/probe results).
func is_game_paused() -> bool:
	if _router._debugger == null or _router._debugger.get_session_id() < 0:
		return false
	var session: Variant = _router._debugger.get_session(_router._debugger.get_session_id())
	return session != null and session.is_breaked()


# -- diagnostics ----------------------------------------------------------------

## The #454 probe-never-connected hint: normally the consuming project has not
## added the probe autoload, but after several play/stop cycles the engine's
## debugger session caps (or its DAP/LSP client caps, which log "max client
## limits reached") can leave the new game silently unattached — name both so
## the failure is diagnosable from the addon alone. Public so
## get_game_scene_tree's soft result (a read-only poll reports state instead of
## refusing) can share the exact same text via the handler.
func probe_never_connected_hint() -> String:
	return (
		"The godot_mcp runtime probe is not connected; add it as an autoload "
		+ "(addons/godot_mcp/mcp_runtime_probe.gd) in the game to enable live "
		+ "inspection. If the autoload IS registered and repeated play/stop cycles "
		+ "precede this, the engine may have exhausted its debugger session/client "
		+ "caps (editor log: \"max client limits reached\") — restart the editor to recover."
	)