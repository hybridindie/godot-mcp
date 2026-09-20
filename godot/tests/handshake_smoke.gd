@tool
extends SceneTree
## Headless behavior test for the server↔addon handshake (issue #530, fixes #521).
##
## Run via: godot --headless --path godot/ --script res://tests/handshake_smoke.gd
## Pins cmd_get_addon_info's envelope shape against the real Godot runtime:
## addon_version flows from plugin.cfg, godot_version is the engine's own, and
## "commands" is the LIVE registered-command list (contains the handshake itself,
## ping, and project info — and never a non-cmd_* name). Wired into pytest by
## tests/contract/test_addon_handshake.py.

const Router := preload("res://addons/godot_mcp/command_router.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	var info: Dictionary = router.handle({
		"id": "1",
		"command": "cmd_get_addon_info",
		"params": {},
	})
	if info.get("id") != "1":
		failures.append("id not echoed: %s" % str(info.get("id")))
	if info.get("ok") != true:
		failures.append("get_addon_info not ok: %s" % str(info))
	var result: Dictionary = info.get("result", {})

	# addon_version flows from plugin.cfg (the CalVer, non-empty).
	var addon_version := str(result.get("addon_version", ""))
	if addon_version.is_empty():
		failures.append("addon_version missing (plugin.cfg unread?): %s" % str(result))
	elif not addon_version.contains("."):
		failures.append("addon_version not a version string: %s" % addon_version)

	# godot_version is the running engine's version string.
	var godot_version := str(result.get("godot_version", ""))
	if not godot_version.begins_with("4."):
		failures.append("godot_version missing/not 4.x: %s" % godot_version)

	# commands is the live registry: handshake + ping + project info present,
	# and every entry carries the cmd_ prefix (no stray keys).
	var commands: Array = result.get("commands", [])
	var names := {}
	for command in commands:
		names[str(command)] = true
		if not str(command).begins_with("cmd_"):
			failures.append("non-cmd_* entry in commands: %s" % str(command))
	for required in ["cmd_get_addon_info", "cmd_ping", "cmd_get_project_info"]:
		if not names.has(required):
			failures.append("commands missing '%s': %s" % [required, str(commands)])
	if commands.size() < 30:
		failures.append("commands suspiciously small (%d) — live registry expected" % commands.size())

	# The version string matches plugin.cfg exactly (single source).
	var cfg := ConfigFile.new()
	var expected_version := ""
	if cfg.load("res://addons/godot_mcp/plugin.cfg") == OK:
		expected_version = str(cfg.get_value("plugin", "version", ""))
	if not expected_version.is_empty() and addon_version != expected_version:
		failures.append("addon_version %s != plugin.cfg %s" % [addon_version, expected_version])

	# #521: cmd_server_hello stores the pushed version for the dock label.
	var hello: Dictionary = router.handle({
		"id": "2",
		"command": "cmd_server_hello",
		"params": {"version": "2026.09.20"},
	})
	if hello.get("ok") != true:
		failures.append("cmd_server_hello not ok: %s" % str(hello))
	if router.server_version != "2026.09.20":
		failures.append("server_version not stored from the hello push: %s" % router.server_version)

	router = null

	if failures.is_empty():
		print("HANDSHAKE_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("HANDSHAKE_TEST_FAIL")
		quit(1)