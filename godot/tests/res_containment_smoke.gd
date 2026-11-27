@tool
extends SceneTree
## Headless behavior test for addon-side res:// containment (issue #909).
##
## Run via: godot --headless --path godot/ --script res://tests/res_containment_smoke.gd
## Pins: MCPHelpers.res_path_error refuses a res:// path that escapes the
## project root (traversal, absolute, backslash, Windows drive, wrong scheme)
## and accepts a contained one (including a harmless `a/../b`); and three
## path-taking handlers refuse an escaping path with VALIDATION_ERROR before
## touching the filesystem. Prints RES_CONTAINMENT_TEST_OK, quits 0 on success.

const Router := preload("res://addons/godot_mcp/command_router.gd")

## Escaping paths; each names a file under the project's parent dir (or an
## absolute dir) so the "no file touched" check can look for it on disk.
const ESCAPING := [
	"res://../mcp_containment_probe.gd",
	"res:///tmp/mcp_containment_probe.gd",
	"res://a/../../mcp_containment_probe.gd",
	"res://a\\..\\..\\mcp_containment_probe.gd",
]


func _initialize() -> void:
	var failures: Array[String] = []
	_test_helper(failures)
	_test_handlers(failures)

	if failures.is_empty():
		print("RES_CONTAINMENT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("RES_CONTAINMENT_TEST_FAIL")
		quit(1)


func _test_helper(failures: Array[String]) -> void:
	# Held as a plain Script so a missing helper fails the test, not the parse.
	var helpers: Script = load("res://addons/godot_mcp/mcp_helpers.gd")
	if not _has_static(helpers, "res_path_error"):
		failures.append("helper: MCPHelpers.res_path_error is missing")
		return
	for bad: String in ESCAPING + ["res://..", "res://C:/x.gd", "user://x.gd", "/etc/x", ""]:
		var hint: String = helpers.call("res_path_error", bad)
		if hint.is_empty():
			failures.append("helper: '%s' should be refused" % bad)
	for good: String in ["res://", "res://a.gd", "res://a/b/c.tscn", "res://a/../b.gd", "res://./x.gd"]:
		var hint: String = helpers.call("res_path_error", good)
		if not hint.is_empty():
			failures.append("helper: '%s' should be accepted, got '%s'" % [good, hint])


func _has_static(script: Script, method: String) -> bool:
	for m: Dictionary in script.get_script_method_list():
		if str(m.get("name", "")) == method:
			return true
	return false


func _test_handlers(failures: Array[String]) -> void:
	var router := Router.new()
	var calls := [
		["cmd_delete_resource_file", "path", ".gd"],
		["cmd_write_script", "script_path", ".gd"],
		["cmd_create_shader", "shader_path", ".gdshader"],
	]
	for c: Array in calls:
		var command: String = c[0]
		var key: String = c[1]
		var ext: String = c[2]
		for bad: String in ESCAPING:
			var path := bad.trim_suffix(".gd") + ext
			var params: Dictionary = {key: path, "content": "extends Node\n", "code": "shader_type spatial;\n"}
			var outside := _outside_file(path)
			# Seed the delete target so a missing refusal would really remove it.
			if command == "cmd_delete_resource_file" and outside != "":
				_write(outside, "probe\n")
			var body: Dictionary = router.handle({"id": "1", "command": command, "params": params})
			if body.get("ok") != false or str(body.get("error", "")) != "VALIDATION_ERROR":
				failures.append("%s('%s'): expected VALIDATION_ERROR, got %s" % [command, path, str(body)])
			if outside != "":
				var exists := FileAccess.file_exists(outside)
				if command == "cmd_delete_resource_file" and not exists:
					failures.append("%s('%s'): deleted a file outside the project" % [command, path])
				elif command != "cmd_delete_resource_file" and exists:
					failures.append("%s('%s'): wrote a file outside the project" % [command, path])
				if exists:
					DirAccess.remove_absolute(outside)
	# A contained-but-missing path passes validation and reaches the existence
	# check (accepted as before, no editor access needed).
	var ok_body: Dictionary = router.handle({
		"id": "2", "command": "cmd_delete_resource_file",
		"params": {"path": "res://a/../mcp_containment_missing.gd"},
	})
	if str(ok_body.get("error", "")) != "RESOURCE_NOT_FOUND":
		failures.append("delete contained path: expected RESOURCE_NOT_FOUND, got %s" % str(ok_body))


## The absolute filesystem location an escaping path would resolve to, or ""
## when it can't be resolved safely (backslash forms stay untouched).
func _outside_file(path: String) -> String:
	if path.contains("\\"):
		return ""
	var rest := path.substr(6)
	if rest.begins_with("/"):
		return rest
	var project := ProjectSettings.globalize_path("res://")
	return project.path_join(rest).simplify_path()


func _write(abs_path: String, text: String) -> void:
	var f := FileAccess.open(abs_path, FileAccess.WRITE)
	if f != null:
		f.store_string(text)
		f.close()
