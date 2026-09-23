@tool
extends SceneTree
## Headless behavior test for the opt-in filesystem auto-refresh (issue #561).
##
## Run via: godot --headless --path godot/ --script res://tests/auto_refresh_smoke.gd
## Verifies MCPAutoRefresh's decision logic (pure, RefCounted — headless-safe):
## the opt-in env parsing (default off, "1"/"true"/"yes" on), the interval
## parsing (default / floor clamp), and the tick guard — scan() must never fire
## while a scan is in flight (re-entrancy, the #417/#453 contract) and must not
## run at all when opted out. Prints AUTO_REFRESH_TEST_OK, quits 0 on success.

const AutoRefresh: GDScript = preload("res://addons/godot_mcp/mcp_auto_refresh.gd")


class FakeFileSystem:
	extends RefCounted
	## Stand-in for EditorFileSystem: records scan() calls; is_scanning is
	## script-controlled to drive the guard.
	var scans := 0
	var scanning := false

	func is_scanning() -> bool:
		return scanning

	func scan() -> void:
		scans += 1


class FakeEnv:
	extends RefCounted
	## A get_env(key) -> String stand-in for OS.get_environment (named so it
	## doesn't shadow Object.get).
	var vars := {}

	func get_env(key: String) -> String:
		return str(vars.get(key, ""))


func _initialize() -> void:
	var failures: Array[String] = []
	_test_opt_in_default_off(failures)
	_test_opt_in_env_var(failures)
	_test_interval_parsing(failures)
	_test_tick_guard(failures)

	if failures.is_empty():
		print("AUTO_REFRESH_TEST_OK")
		quit(0)
	else:
		push_error("AUTO_REFRESH_FAILURES: %s" % [str(failures)])
		quit(1)


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])


func _test_opt_in_default_off(failures: Array[String]) -> void:
	# Default: OFF — the timer never scans (byte-identical to today).
	var env := FakeEnv.new()
	_eq(failures, "default_off", AutoRefresh.enabled_from_env(env.get_env), false)
	_eq(failures, "off_tick", AutoRefresh.tick(false, FakeFileSystem.new()), false)


func _test_opt_in_env_var(failures: Array[String]) -> void:
	# GODOT_MCP_AUTO_REFRESH=1/true/yes opts in; anything else stays off.
	var env := FakeEnv.new()
	for on_value in ["1", "true", "yes", "TRUE", "Yes"]:
		env.vars[AutoRefresh.ENV_VAR] = on_value
		_eq(failures, "on_%s" % on_value, AutoRefresh.enabled_from_env(env.get_env), true)
	for off_value in ["", "0", "no", "off", "banana"]:
		env.vars[AutoRefresh.ENV_VAR] = off_value
		_eq(failures, "off_%s" % (off_value if off_value != "" else "empty"), AutoRefresh.enabled_from_env(env.get_env), false)


func _test_interval_parsing(failures: Array[String]) -> void:
	var env := FakeEnv.new()
	_eq(failures, "interval.default", AutoRefresh.interval_from_env(env.get_env), AutoRefresh.DEFAULT_INTERVAL)
	env.vars["GODOT_MCP_AUTO_REFRESH_INTERVAL"] = "5"
	_eq(failures, "interval.5", AutoRefresh.interval_from_env(env.get_env), 5.0)
	env.vars["GODOT_MCP_AUTO_REFRESH_INTERVAL"] = "0.5"
	_eq(failures, "interval.floor", AutoRefresh.interval_from_env(env.get_env), 2.0)
	env.vars["GODOT_MCP_AUTO_REFRESH_INTERVAL"] = "garbage"
	_eq(failures, "interval.garbage_default", AutoRefresh.interval_from_env(env.get_env), AutoRefresh.DEFAULT_INTERVAL)


func _test_tick_guard(failures: Array[String]) -> void:
	# Enabled: a tick calls scan() exactly once; a tick while is_scanning()
	# calls nothing (re-entrancy guard, #417/#453 family).
	var fs := FakeFileSystem.new()
	_eq(failures, "enabled.one_scan", AutoRefresh.tick(true, fs), true)
	_eq(failures, "enabled.scan_count", fs.scans, 1)
	fs.scanning = true
	_eq(failures, "in_flight.no_scan", AutoRefresh.tick(true, fs), false)
	_eq(failures, "in_flight.scan_count", fs.scans, 1)
	fs.scanning = false
	_eq(failures, "resumed.one_more", AutoRefresh.tick(true, fs), true)
	_eq(failures, "resumed.scan_count", fs.scans, 2)
	# A null fs seam (headless/no-editor) is a no-op, not a crash.
	_eq(failures, "null_fs", AutoRefresh.tick(true, null), false)