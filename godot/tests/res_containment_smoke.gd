@tool
extends SceneTree
## Headless behavior test for addon-side res:// containment (issue #909).
##
## Run via: godot --headless --path godot/ --script res://tests/res_containment_smoke.gd
## Pins: MCPPaths.res_path_error (and MCPHelpers.res_path_error, which
## delegates) refuses a res:// path that escapes the project root (traversal at
## any depth, absolute, backslash, Windows drive, wrong scheme) and accepts a
## contained one (including a harmless `a/../b`); and EVERY path-taking handler
## refuses an escaping path with VALIDATION_ERROR before touching the
## filesystem. The table below names each command + param key, so deleting one
## handler's check fails this smoke. Prints RES_CONTAINMENT_TEST_OK, quits 0 on
## success.

const Router := preload("res://addons/godot_mcp/command_router.gd")

## Helper-only escaping paths (no file behind them). The even-count `..` forms
## are the ones an engine-version-dependent simplify_path collapses to a
## contained path, so the normaliser must catch them on its own.
const HELPER_ESCAPING := [
	"res://..",
	"res://../x.gd",
	"res://../../x.gd",
	"res://a/../../x.gd",
	"res://a/../../../x.gd",
	"res://a/b/../../../../x.gd",
	"res:///abs/x.gd",
	"res://C:/x.gd",
	"res://C:x.gd",
	"res://c:x.gd",
	"res://a:b.gd",
	"res://a\\..\\..\\x.gd",
	"user://x.gd",
	"/etc/x",
	"",
]
const HELPER_CONTAINED := [
	"res://",
	"res://a.gd",
	"res://a/b/c.tscn",
	"res://a/../b.gd",
	"res://./x.gd",
	"res://a//b.gd",
	"res://a/b/../../c.gd",
	"res://ab:c.gd",
]

const ICON := "res://addons/godot_mcp/icon.png"

## Every path-taking command: [command, param key, extension, extra params].
## Extension "/" marks a directory param. Extras satisfy the checks that run
## before or alongside the path guard so only containment decides the result.
const COMMANDS := [
	["cmd_delete_resource_file", "path", ".gd", {}],
	["cmd_move_resource_file", "path", ".gd", {"new_path": "res://mcp_containment_moved.gd"}],
	["cmd_move_resource_file", "new_path", ".gd", {"path": "res://mcp_containment_missing.gd"}],
	["cmd_path_to_uid", "path", ".gd", {}],
	["cmd_get_filesystem_tree", "directory", "/", {}],
	["cmd_search_files", "directory", "/", {"pattern": "*"}],
	["cmd_read_script", "script_path", ".gd", {}],
	["cmd_list_scripts", "directory", "/", {}],
	["cmd_write_script", "script_path", ".gd", {"content": "extends Node\n"}],
	["cmd_patch_script", "script_path", ".gd", {"find": "probe", "replace": "patched"}],
	["cmd_create_shader", "shader_path", ".gdshader", {"code": "shader_type spatial;\n"}],
	["cmd_read_shader", "shader_path", ".gdshader", {}],
	["cmd_assign_shader_material", "shader_path", ".gdshader", {"node_path": "."}],
	["cmd_create_visual_shader", "path", ".tres", {"name": "probe"}],
	["cmd_add_shader_node", "shader_path", ".tres", {"node_id": 2, "type": "VisualShaderNodeColorConstant"}],
	["cmd_connect_shader_nodes", "shader_path", ".tres", {"from_node": 2, "from_port": 0, "to_node": 0, "to_port": 0}],
	["cmd_set_shader_node_param", "shader_path", ".tres", {"node_id": 2, "property": "constant", "value": 1}],
	["cmd_read_visual_shader", "shader_path", ".tres", {}],
	["cmd_create_shader_group", "shader_path", ".tres", {"name": "g", "node_id": 2}],
	["cmd_rename_shader_group", "shader_path", ".tres", {"name": "g", "node_id": 2}],
	["cmd_remove_shader_group", "shader_path", ".tres", {"node_id": 2}],
	["cmd_add_shader_group_node", "shader_path", ".tres", {"group_node_id": 2, "node_id": 2, "type": "VisualShaderNodeColorConstant"}],
	["cmd_remove_shader_group_node", "shader_path", ".tres", {"group_node_id": 2, "node_id": 2}],
	["cmd_import_asset", "target_path", ".png", {"source": ICON}],
	["cmd_get_import_status", "target_path", ".png", {}],
	["cmd_create_material_from_textures", "path", ".tres", {}],
	["cmd_create_material_from_textures", "albedo", ".png", {"path": "res://mcp_containment_mat.tres"}],
	["cmd_get_dependencies", "path", ".tscn", {}],
	["cmd_create_mesh_library", "save_path", ".tres", {}],
	["cmd_add_mesh_library_item", "library_path", ".tres", {"mesh_type": "BoxMesh"}],
	["cmd_add_mesh_library_item", "mesh_path", ".tres", {"library_path": "res://mcp_containment_missing.tres"}],
	["cmd_create_tileset", "save_path", ".tres", {}],
	["cmd_add_tileset_atlas_source", "tileset_path", ".tres", {"texture_path": ICON}],
	["cmd_add_tileset_atlas_source", "texture_path", ".png", {"tileset_path": "res://mcp_containment_missing.tres"}],
	["cmd_create_tile", "tileset_path", ".tres", {"source_id": 0, "atlas_coords": [0, 0]}],
	["cmd_run_project_tool", "script", ".gd", {"function": "run"}],
	["cmd_play_scene", "scene_path", ".tscn", {}],
	["cmd_close_scene", "scene_path", ".tscn", {}],
	["cmd_open_scene", "scene_path", ".tscn", {}],
	["cmd_reload_scene", "scene_path", ".tscn", {"confirm": true}],
	["cmd_instance_scene", "scene_path", ".tscn", {"parent_path": "."}],
	["cmd_extract_scene", "scene_path", ".tscn", {"node_path": "."}],
	["cmd_create_theme", "save_path", ".tres", {}],
	["cmd_read_resource", "resource_path", ".tres", {}],
	["cmd_create_resource", "resource_path", ".tres", {"type": "Resource"}],
	["cmd_set_resource_property", "resource_path", ".tres", {"property": "resource_name", "value": "x"}],
	["cmd_register_autoload", "path", ".gd", {"name": "McpContainmentProbe"}],
	["cmd_add_audio_player", "stream_path", ".wav", {"parent_path": "."}],
	["cmd_set_breakpoint", "path", ".gd", {"line": 1}],
	["cmd_remove_breakpoint", "path", ".gd", {"line": 1}],
	["cmd_attach_script", "script_path", ".gd", {"node_path": "."}],
	["cmd_create_scene", "scene_path", ".tscn", {"root_type": "Node"}],
	["cmd_compose_node", "script_path", ".gd", {"node_type": "Node", "name": "Probe"}],
]

const PROBE_TEXT := "probe\n"

var _probe_dir := ""


func _initialize() -> void:
	var failures: Array[String] = []
	_probe_dir = OS.get_cache_dir().path_join("mcp_res_containment")
	DirAccess.make_dir_recursive_absolute(_probe_dir)
	var router := Router.new()
	_test_helper(failures)
	_test_handlers(router, failures)
	_test_cross_scene(router, failures)
	_test_contained(router, failures)

	if failures.is_empty():
		print("RES_CONTAINMENT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("RES_CONTAINMENT_TEST_FAIL")
		quit(1)


func _test_helper(failures: Array[String]) -> void:
	# Held as plain Scripts so a missing helper fails the test, not the parse.
	for script_path: String in ["res://addons/godot_mcp/mcp_paths.gd", "res://addons/godot_mcp/mcp_helpers.gd"]:
		if not ResourceLoader.exists(script_path):
			failures.append("helper: %s is missing" % script_path)
			continue
		var script: Script = load(script_path)
		if not _has_static(script, "res_path_error"):
			failures.append("helper: %s has no res_path_error" % script_path)
			continue
		for bad: String in HELPER_ESCAPING:
			var hint: String = script.call("res_path_error", bad)
			if hint.is_empty():
				failures.append("helper %s: '%s' should be refused" % [script_path.get_file(), bad])
		for good: String in HELPER_CONTAINED:
			var hint: String = script.call("res_path_error", good)
			if not hint.is_empty():
				failures.append("helper %s: '%s' should be accepted, got '%s'" % [script_path.get_file(), good, hint])
		# The escape hint is specific, so the handlers can pass it through.
		var escape_hint: String = script.call("res_path_error", "res://../../x.gd")
		if not escape_hint.contains("escapes the project root"):
			failures.append("helper %s: hint should say 'escapes the project root', got '%s'" % [script_path.get_file(), escape_hint])


func _has_static(script: Script, method: String) -> bool:
	for m: Dictionary in script.get_script_method_list():
		if str(m.get("name", "")) == method:
			return true
	return false


## The escaping forms for one probe: [res:// path, absolute probe file or ""].
## The `..` forms resolve (through Godot's res:// mapping) to a probe under the
## user cache dir, so a missing check would really touch that file.
func _escaping_paths(ext: String) -> Array:
	var project := ProjectSettings.globalize_path("res://")
	var ups := ""
	for _part: String in project.split("/", false):
		ups += "../"
	var is_dir := ext == "/"
	var file_name := "" if is_dir else "mcp_containment_probe" + ext
	var target := _probe_dir if is_dir else _probe_dir.path_join(file_name)
	var probe := "" if is_dir else target
	var rel := ups + target.trim_prefix("/")
	var suffix := "" if is_dir else ext
	return [
		["res://" + rel, probe],
		["res://a/../" + rel, probe],
		["res://a/b/../../" + rel, probe],
		["res://" + target, ""],
		["res://a\\..\\..\\probe" + suffix, ""],
		["res://C:probe" + suffix, ""],
	]


func _test_handlers(router: RefCounted, failures: Array[String]) -> void:
	for c: Array in COMMANDS:
		var command: String = c[0]
		var key: String = c[1]
		var ext: String = c[2]
		var extras: Dictionary = c[3]
		for pair: Array in _escaping_paths(ext):
			var path: String = pair[0]
			var probe: String = pair[1]
			# Seed the probe so a missing check that deletes, moves, overwrites
			# or reads it is caught by the content check below.
			if probe != "":
				_write(probe, PROBE_TEXT)
			var params: Dictionary = extras.duplicate()
			params[key] = path
			var body: Dictionary = router.call("handle", {"id": "1", "command": command, "params": params})
			var label := "%s(%s='%s')" % [command, key, path]
			if body.get("ok") != false or str(body.get("error", "")) != "VALIDATION_ERROR":
				failures.append("%s: expected VALIDATION_ERROR, got %s" % [label, str(body)])
			elif not str(body.get("hint", "")).contains("res://"):
				failures.append("%s: hint should name the res:// rule, got '%s'" % [label, str(body.get("hint", ""))])
			if probe != "":
				if not FileAccess.file_exists(probe):
					failures.append("%s: removed a file outside the project" % label)
				elif FileAccess.get_file_as_string(probe) != PROBE_TEXT:
					failures.append("%s: rewrote a file outside the project" % label)
				DirAccess.remove_absolute(probe)


## cross_scene_set_property reports per-scene errors inside an ok envelope.
func _test_cross_scene(router: RefCounted, failures: Array[String]) -> void:
	for pair: Array in _escaping_paths(".tscn"):
		var path: String = pair[0]
		var body: Dictionary = router.call("handle", {
			"id": "3", "command": "cmd_cross_scene_set_property",
			"params": {"scenes": [path], "type": "Node", "property": "name", "value": "x"},
		})
		var result: Dictionary = body.get("result", {}) if body.get("result") is Dictionary else {}
		var results: Array = result.get("results", [])
		var first: Dictionary = results[0] if not results.is_empty() else {}
		if str(first.get("error", "")).is_empty() or int(first.get("modified", -1)) != 0:
			failures.append("cmd_cross_scene_set_property('%s'): expected a per-scene refusal, got %s" % [path, str(body)])
		elif not str(first.get("hint", "")).contains("res://"):
			failures.append("cmd_cross_scene_set_property('%s'): hint should name the res:// rule, got %s" % [path, str(first)])


## Contained-but-missing paths pass validation and reach the existence check
## (accepted as before, no editor access needed).
func _test_contained(router: RefCounted, failures: Array[String]) -> void:
	var cases := [
		["cmd_delete_resource_file", {"path": "res://a/../mcp_containment_missing.gd"}],
		["cmd_read_script", {"script_path": "res://a/../mcp_containment_missing.gd"}],
		["cmd_read_shader", {"shader_path": "res://a/../mcp_containment_missing.gdshader"}],
		["cmd_read_resource", {"resource_path": "res://a/../mcp_containment_missing.tres"}],
	]
	for c: Array in cases:
		var body: Dictionary = router.call("handle", {"id": "2", "command": c[0], "params": c[1]})
		if str(body.get("error", "")) != "RESOURCE_NOT_FOUND":
			failures.append("%s contained path: expected RESOURCE_NOT_FOUND, got %s" % [c[0], str(body)])


func _write(abs_path: String, text: String) -> void:
	var f := FileAccess.open(abs_path, FileAccess.WRITE)
	if f != null:
		f.store_string(text)
		f.close()
