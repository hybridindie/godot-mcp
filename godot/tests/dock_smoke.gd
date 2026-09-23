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

	# === Project / scene / selected node ===
	dock.set_project_path("res://demo")
	_expect(failures, "project", dock.displayed_project(), "res://demo")
	dock.set_active_scene("Main")
	_expect(failures, "scene", dock.displayed_scene(), "Main")
	dock.set_selected_node("Player")
	_expect(failures, "selected", dock.displayed_selected(), "Player")

	# === Empty values fall back to a readable placeholder ===
	dock.set_server_version("")
	_expect(failures, "server_version_placeholder", dock.displayed_server_version(), "(unknown)")
	dock.set_active_scene("")
	_expect(failures, "scene_placeholder", dock.displayed_scene(), "(none)")
	dock.set_selected_node("")
	_expect(failures, "selected_placeholder", dock.displayed_selected(), "(none)")

	# === Enabled toolsets ===
	dock.set_enabled_toolsets(PackedStringArray(["core", "scene_edit", "testing"]))
	_expect(failures, "toolsets", dock.displayed_toolsets(), "core, scene_edit, testing")
	# Empty toolsets shows placeholder
	dock.set_enabled_toolsets(PackedStringArray())
	_expect(failures, "toolsets_empty", dock.displayed_toolsets(), "(none)")

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

	# === Recent-command log keeps only the last 10 entries ===
	for i in range(15):
		dock.log_command("cmd_%d" % i)
	var recent := dock.get_recent_commands()
	if recent.size() != 10:
		failures.append("log size: expected 10, got %d" % recent.size())
	else:
		# Entries are now "[HH:MM:SS] cmd_N" — check the command part.
		if not recent[0].ends_with(" cmd_5"):
			failures.append("log_first: expected '... cmd_5', got %s" % recent[0])
		if not recent[9].ends_with(" cmd_14"):
			failures.append("log_last: expected '... cmd_14', got %s" % recent[9])
	if not dock.displayed_log().contains("cmd_14"):
		failures.append("log label missing newest entry 'cmd_14'")
	if dock.displayed_log().contains("cmd_4"):
		failures.append("log label still shows evicted entry 'cmd_4'")

	# === Command count increments on log_command ===
	if dock.get_command_count() != 15:
		failures.append("command_count: expected 15, got %d" % dock.get_command_count())

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