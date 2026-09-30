@tool
extends SceneTree
## Headless behavior test for the MCP status dock (issue #2).
##
## Run via: godot --headless --path godot/ --script res://tests/dock_smoke.gd
## Exercises mcp_dock.gd's public state API WITHOUT the editor — the dock is a
## dumb, editor-independent Control fed by the plugin, so it can be verified with
## no EditorInterface present. Prints DOCK_TEST_OK and quits 0 on success;
## prints each failure and DOCK_TEST_FAIL, quits 1 otherwise.
##
## The pytest wrapper tests/integration/test_addon_dock.py runs this and asserts
## on its exit code + output.

const MCPDockScript := preload("res://addons/godot_mcp/mcp_dock.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var dock := MCPDockScript.new()

	# === Connection status ===
	dock.set_connection_status(MCPDockScript.ConnectionStatus.CONNECTED)
	_expect(failures, "connection", dock.displayed_connection(), "Connected")
	dock.set_connection_status(MCPDockScript.ConnectionStatus.CONNECTING)
	_expect(failures, "connecting", dock.displayed_connection(), "Connecting…")
	dock.set_connection_status(MCPDockScript.ConnectionStatus.DISCONNECTED)
	_expect(failures, "disconnected", dock.displayed_connection(), "Disconnected")
	# #593: a taken-over link is its own state — never a green "Connected".
	dock.set_connection_status(MCPDockScript.ConnectionStatus.REPLACED)
	_expect(
		failures, "replaced", dock.displayed_connection(), "Replaced by another editor"
	)

	# === Project / scene / selected node ===
	dock.set_project_path("res://demo")
	_expect(failures, "project", dock.displayed_project(), "res://demo")
	dock.set_active_scene("Main")
	_expect(failures, "scene", dock.displayed_scene(), "Main")
	dock.set_selected_node("Player")
	_expect(failures, "selected", dock.displayed_selected(), "Player")

	# #590: the undo guarantee is visible — last action + how to revert.
	dock.set_last_action("create_node 'Player'")
	_expect(
		failures, "last_action", dock.displayed_last_action(),
		"create_node 'Player' (Ctrl+Z to undo)"
	)
	dock.set_last_action("")
	_expect(failures, "last_action_placeholder", dock.displayed_last_action(), "(none)")

	# === #591: dirty-scene marker + play/probe row ===
	dock.set_scene_dirty("main.tscn", false)
	_expect(failures, "scene_clean", dock.displayed_scene(), "main.tscn")
	dock.set_scene_dirty("main.tscn", true)
	_expect(failures, "scene_dirty", dock.displayed_scene(), "main.tscn ●")
	# A dirty marker only makes sense with a named scene.
	dock.set_scene_dirty("", true)
	_expect(failures, "scene_dirty_nameless", dock.displayed_scene(), "(none)")

	dock.set_play_state(false, false)
	_expect(failures, "play_not_playing", dock.displayed_play_state(), "(none)")
	dock.set_play_state(true, true, "main.tscn")
	_expect(failures, "play_with_probe", dock.displayed_play_state(), "main.tscn (probe connected)")
	dock.set_play_state(true, false, "main.tscn")
	_expect(failures, "play_no_probe", dock.displayed_play_state(), "main.tscn (no probe)")

	# === Empty values fall back to a readable placeholder ===
	dock.set_server_version("")
	_expect(failures, "server_version_placeholder", dock.displayed_server_version(), "(unknown)")
	dock.set_active_scene("")
	_expect(failures, "scene_placeholder", dock.displayed_scene(), "(none)")
	dock.set_selected_node("")
	_expect(failures, "selected_placeholder", dock.displayed_selected(), "(none)")

	# === Enabled toolsets (#592: fed by the server's push, not dead code) ===
	# Before the first push the set is unknown — NOT "(none)", which was the lie.
	if dock.displayed_toolsets() != "(unknown)":
		failures.append("toolsets_initial_unknown: expected '(unknown)', got %s" % dock.displayed_toolsets())
	dock.set_enabled_toolsets(PackedStringArray(["core", "scene_edit", "testing"]))
	_expect(failures, "toolsets", dock.displayed_toolsets(), "core, scene_edit, testing")
	# An empty pushed set is genuinely "(none)" (the server has only core? no —
	# core is always present, but the setter still handles empty).
	dock.set_enabled_toolsets(PackedStringArray())
	_expect(failures, "toolsets_empty", dock.displayed_toolsets(), "(none)")
	# An older server that never pushes: explicit unknown.
	dock.set_toolsets_unknown()
	_expect(failures, "toolsets_unknown", dock.displayed_toolsets(), "(unknown)")

	# === Command statistics: total, last exec (#520: no latency field — the
	# addon can only measure handler-exec time honestly) ===
	dock.set_command_stats(42, 15.3)
	_expect(failures, "cmd_count", dock.displayed_command_count(), "42")
	# Last exec is formatted as "X.X ms"
	if not dock.displayed_last_exec().contains("15.3"):
		failures.append("last_exec: expected '15.3 ms', got %s" % dock.displayed_last_exec())
	# Zero exec shows placeholder
	dock.set_command_stats(0, 0.0)
	_expect(failures, "cmd_count_zero", dock.displayed_command_count(), "0")
	_expect(failures, "last_exec_zero", dock.displayed_last_exec(), "(none)")

	# === Recent-command log: outcomes (#589) + depth 50 (#594) ===
	# #589: entries carry the command's OUTCOME — dispatch-time entries are gone;
	# the log is fed from command completion (ok / error code). #594: depth is 50
	# so a 20-command burst (batch_set_property / run_commands) no longer evicts
	# the interesting entries.
	for i in range(15):
		dock.log_command_result("cmd_%d" % i, true, "")
	var recent := dock.get_recent_commands()
	if recent.size() != 15:
		failures.append("log size: expected 15 (no eviction under depth 50), got %d" % recent.size())
	else:
		# Entries are "[HH:MM:SS] cmd_N ✓" — check the command part.
		if not recent[0].contains(" cmd_0"):
			failures.append("log_first: expected '... cmd_0', got %s" % recent[0])
		if not recent[14].contains(" cmd_14"):
			failures.append("log_last: expected '... cmd_14', got %s" % recent[14])
		# Success lines end with the ✓ marker.
		if not recent[14].ends_with("✓"):
			failures.append("log_ok_marker: expected '... ✓', got %s" % recent[14])
	if not dock.displayed_log().contains("cmd_14"):
		failures.append("log label missing newest entry 'cmd_14'")

	# === #594: the log survives a 20-command burst without evicting ===
	# (batch_set_property / run_commands fire 20+; depth 50 keeps them all.)
	for i in range(20):
		dock.log_command_result("cmd_burst_%d" % i, true, "")
	if dock.get_recent_commands().size() != 35:
		failures.append("burst depth: expected 35 entries retained, got %d" % dock.get_recent_commands().size())
	if not dock.displayed_log().contains("cmd_burst_19"):
		failures.append("burst newest entry missing from the log")

	# === #594: eviction still applies past the 50-entry depth ===
	for i in range(40):
		dock.log_event("drain_%d" % i)
	if dock.get_recent_commands().size() != 50:
		failures.append("depth cap: expected 50 entries, got %d" % dock.get_recent_commands().size())

	# === #589: failed commands carry the error code in the log line ===
	dock.log_command_result("cmd_delete_node", false, "PRECONDITION_FAILED")
	var last := dock.get_recent_commands()[dock.get_recent_commands().size() - 1]
	if not last.contains("cmd_delete_node"):
		failures.append("log_failed_cmd: expected the command name, got %s" % last)
	if not last.contains("PRECONDITION_FAILED"):
		failures.append("log_failed_code: expected the error code in the line, got %s" % last)
	if not last.contains("✗"):
		failures.append("log_fail_marker: expected the ✗ marker, got %s" % last)
	if not dock.displayed_log().contains("✗ PRECONDITION_FAILED"):
		failures.append("log_failed_render: displayed log must contain '✗ PRECONDITION_FAILED'")

	# === #593: bridge lifecycle notices share the same log ===
	dock.log_event("reconnecting (attempt 2, next in 2.0s)")
	var events := dock.get_recent_commands()
	var last_event := events[events.size() - 1]
	if not last_event.contains("reconnecting (attempt 2"):
		failures.append("log_event_missing: expected the reconnect line, got %s" % last_event)
	if not last_event.begins_with("["):
		failures.append("log_event_timestamp: expected '[HH:MM:SS] ...', got %s" % last_event)
	# The event line is not a command outcome — it must not inflate the count.
	# (count was 36 after the 15 loop + 20 burst + 1 failed command above.)
	if dock.get_command_count() != 36:
		failures.append("log_event_count: expected count unchanged at 36, got %d" % dock.get_command_count())
	# A notice evicts the same way command outcomes do, sharing the 50-deep cap.
	for i in range(60):
		dock.log_event("event_%d" % i)
	if dock.get_recent_commands().size() != 50:
		failures.append("log_event_eviction: expected 50 entries, got %d" % dock.get_recent_commands().size())

	# === #589: the log_command (dispatch-time, name-only) path is gone ===
	if MCPDockScript.new().has_method("log_command"):
		failures.append("legacy dispatch-time log_command must be replaced by log_command_result (#589)")

	# === Command count increments on log_command_result (15 + 20 burst + 1 = 36) ===
	if dock.get_command_count() != 36:
		failures.append("command_count: expected 36, got %d" % dock.get_command_count())

	# === #594: the count is SESSION-scoped — a fresh reconnect resets it ===
	dock.log_command_result("cmd_after_session", true, "")
	if dock.get_command_count() != 37:
		failures.append("pre_reset_count: expected 37, got %d" % dock.get_command_count())
	dock.set_connection_status(MCPDockScript.ConnectionStatus.CONNECTING)
	dock.set_connection_status(MCPDockScript.ConnectionStatus.CONNECTED)
	if dock.get_command_count() != 0:
		failures.append("session_reset: expected 0 after reconnect, got %d" % dock.get_command_count())
	if dock.displayed_command_count() != "0":
		failures.append("session_reset_label: expected '0', got %s" % dock.displayed_command_count())

	# === #594: copy button exists and the copy path is safe on empty ===
	var empty_dock := MCPDockScript.new()
	empty_dock.copy_log_to_clipboard()  # empty log → no-op, must not error
	if not empty_dock.has_method("copy_log_to_clipboard"):
		failures.append("copy_log_to_clipboard method missing (#594)")
	empty_dock.free()

	# === Timestamp format: entries start with [HH:MM:SS] ===
	if not recent[0].begins_with("["):
		failures.append("timestamp_format: expected '[HH:MM:SS] ...', got %s" % recent[0])

	# === Auto-refresh toggle (issue #561) ===
	if dock.displayed_auto_refresh() != false:
		failures.append("auto_refresh_default: expected false, got %s" % dock.displayed_auto_refresh())
	var got_toggle := [false]
	dock.auto_refresh_toggled.connect(func(on: bool) -> void: got_toggle[0] = on)
	dock.set_auto_refresh(true)
	if dock.displayed_auto_refresh() != true:
		failures.append("auto_refresh_set: expected true, got %s" % dock.displayed_auto_refresh())
	# set_auto_refresh must not emit (plugin-init sync); toggling via the checkbox does.
	# The checkbox is already pressed=true (set_auto_refresh synced it silently),
	# so toggle down-then-up: a same-value set_pressed emits nothing (verified live).
	if got_toggle[0] != false:
		failures.append("auto_refresh_set_no_signal: set_auto_refresh emitted the signal")
	dock._auto_refresh_check.set_pressed(false)
	dock._auto_refresh_check.set_pressed(true)
	if got_toggle[0] != true:
		failures.append("auto_refresh_toggle_signal: checkbox toggle did not emit")
	dock.set_auto_refresh(false)
	if dock.displayed_auto_refresh() != false:
		failures.append("auto_refresh_unset: expected false, got %s" % dock.displayed_auto_refresh())

	dock.free()

	if failures.is_empty():
		print("DOCK_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("DOCK_TEST_FAIL")
		quit(1)


func _expect(failures: Array[String], label: String, got: String, want: String) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, want, got])