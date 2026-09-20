@tool
extends SceneTree
## Headless behavior test for the consolidated runtime guards (issue #527).
##
## Run via: godot --headless --path godot/ --script res://tests/guards_smoke.gd
## Exercises MCPGuards with no editor and no debugger attached — every guard
## fails the same structured way (PRECONDITION_FAILED + required key), the
## #454 diagnostic text is single-sourced, and the router's delegating wrappers
## match the shared implementation. Prints GUARDS_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	# Inject the play-session oracle: in headless -s mode the EditorInterface
	# singleton exists but play APIs are unavailable (ClassDB knows the method,
	# the singleton doesn't expose it) — so the smoke overrides the oracle and
	# drives both branches deterministically.
	var guards := router._guards
	guards.set_play_session_oracle(func() -> bool: return true)

	# Live session, no debugger attached yet (headless): play passes, then the
	# debug-session/probe guards fail at their next link.
	var debug: Dictionary = router._require_debug_session()
	if bool(debug.get("ok", false)):
		failures.append("debug guard should refuse with no debugger: %s" % str(debug))
	else:
		_expect(failures, "debug.error", debug.get("error"), "INTERNAL_ERROR")
	var probe: Dictionary = router._require_live_probe()
	_expect(failures, "probe.error", probe.get("error"), "INTERNAL_ERROR")

	# The unpaused guard composes live-probe first: same INTERNAL_ERROR here.
	var unpaused: Dictionary = guards.require_unpaused_live_probe()
	_expect(failures, "unpaused.error", unpaused.get("error"), "INTERNAL_ERROR")

	# Now no play session at all — every guard refuses with play_session.
	guards.set_play_session_oracle(func() -> bool: return false)
	var play: Dictionary = guards.require_play_session()
	_expect(failures, "play.ok", play.get("ok"), false)
	_expect(failures, "play.error", play.get("error"), "PRECONDITION_FAILED")
	_expect(failures, "play.required", play.get("required"), "play_session")
	if not str(play.get("hint", "")).contains("play_scene"):
		failures.append("play.hint: should name the recovery tool: %s" % str(play.get("hint")))
	debug = router._require_debug_session()
	_expect(failures, "debug.required", debug.get("required"), "play_session")
	probe = router._require_live_probe()
	_expect(failures, "probe.required", probe.get("required"), "play_session")
	unpaused = guards.require_unpaused_live_probe()
	_expect(failures, "unpaused.required", unpaused.get("required"), "play_session")

	# is_game_paused degrades to false with no debugger (never crashes).
	_expect(failures, "paused_no_debugger", guards.is_game_paused(), false)

	# The #454 diagnostic is single-sourced: the guard module owns the text,
	# runtime_session consumes it via probe_never_connected_hint().
	var hint := guards.probe_never_connected_hint()
	if not hint.contains("max client limits"):
		failures.append("hint: missing the #454 recovery diagnostic: %s" % hint)
	if not hint.contains("mcp_runtime_probe.gd"):
		failures.append("hint: missing the autoload reminder: %s" % hint)

	router = null

	if failures.is_empty():
		print("GUARDS_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("GUARDS_TEST_FAIL")
		quit(1)


func _expect(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if typeof(got) != typeof(want) or got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])