@tool
class_name MCPProjectScaffoldHandlers
extends RefCounted
## Domain handler: project scaffold (issue #112).
##
## Generates a project skeleton (directories, settings, autoloads, root scene)
## for common game types so agents start from a known structure.
##
## #700: the scaffold is all-or-nothing. Every step runs against an in-memory
## settings transaction and a file/directory snapshot; any failure rolls back
## the files, autoload, and project settings before returning a structured error.
##
## Registered by the router on _init().

const DIRS := ["res://scenes/", "res://scripts/", "res://assets/", "res://shaders/"]
const GAME_STATE_SCRIPT := "res://scripts/game_state.gd"
const PROJECT_FILE := "res://project.godot"
const SETTING_KEYS := [
	"application/config/name",
	"display/window/size/viewport_width",
	"display/window/size/viewport_height",
	"rendering/renderer/rendering_method",
	"physics/2d/default_gravity",
	"physics/3d/default_gravity",
	"application/run/main_scene",
	"autoload/GameState",
]

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_scaffold_project"] = _cmd_scaffold_project


# -- helpers -----------------------------------------------------------------

func _ensure_dir(path: String) -> int:
	var abs := ProjectSettings.globalize_path(path)
	if DirAccess.dir_exists_absolute(abs):
		return OK
	return DirAccess.make_dir_recursive_absolute(abs)


func _write_text(path: String, text: String) -> int:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return FileAccess.get_open_error()
	file.store_string(text)
	file.close()
	EditorInterface.get_resource_filesystem().update_file(path)
	return OK


func _write_script(path: String, code: String) -> int:
	return _write_text(path, code)


func _write_packed_scene(root: Node, path: String) -> int:
	var scene := PackedScene.new()
	var err := scene.pack(root)
	if err != OK:
		return err
	err = ResourceSaver.save(scene, path)
	if err == OK:
		EditorInterface.get_resource_filesystem().update_file(path)
	return err


func _snapshot(main_scene_path: String) -> Dictionary:
	var settings := {}
	for key in SETTING_KEYS:
		settings[key] = {
			"had": ProjectSettings.has_setting(key),
			"value": ProjectSettings.get_setting(key),
		}
	var dirs := {}
	for path in DIRS:
		dirs[path] = DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(path))
	var files := {}
	for path in [GAME_STATE_SCRIPT, main_scene_path]:
		var existed := FileAccess.file_exists(path)
		var uid_path := str(path) + ".uid"
		var uid_existed := FileAccess.file_exists(uid_path)
		files[path] = {
			"existed": existed,
			"text": FileAccess.get_file_as_string(path) if existed else "",
			"uid_existed": uid_existed,
			"uid_text": FileAccess.get_file_as_string(uid_path) if uid_existed else "",
		}
	return {
		"settings": settings,
		"dirs": dirs,
		"files": files,
		"project_text": FileAccess.get_file_as_string(PROJECT_FILE),
	}


func _step_failed(step: String, detail: String) -> Dictionary:
	return {"ok": false, "step": step, "error": detail}


func _rollback(snapshot: Dictionary) -> Dictionary:
	var errors: Array[String] = []

	# Restore files that existed; remove files this run created (plus .uid sidecars).
	for path in snapshot["files"]:
		var state: Dictionary = snapshot["files"][path]
		if state["existed"]:
			var write_err := _write_text(path, str(state["text"]))
			if write_err != OK:
				errors.append("could not restore '%s' (error %d)" % [path, write_err])
			# Godot 4.4+ sidecars: restore the original UID, or drop a sidecar that
			# the scan created for a pre-4.4 file.
			var uid_path: String = str(path) + ".uid"
			if state["uid_existed"]:
				var uid_err := _write_text(uid_path, str(state["uid_text"]))
				if uid_err != OK:
					errors.append("could not restore '%s' (error %d)" % [uid_path, uid_err])
			elif FileAccess.file_exists(uid_path):
				DirAccess.remove_absolute(uid_path)
				EditorInterface.get_resource_filesystem().update_file(uid_path)
		else:
			_router._remove_file_with_uid(path)

	# Drop only the directories this run created (deepest first).
	for i in range(DIRS.size() - 1, -1, -1):
		var path: String = DIRS[i]
		if snapshot["dirs"][path]:
			continue
		var abs := ProjectSettings.globalize_path(path)
		if DirAccess.dir_exists_absolute(abs):
			var dir_err := DirAccess.remove_absolute(abs)
			if dir_err != OK:
				errors.append("could not remove '%s' (error %d)" % [path, dir_err])

	# Refresh the Autoload panel before restoring the settings snapshot.
	var autoload_key := "autoload/GameState"
	if not snapshot["settings"][autoload_key]["had"] \
			and ProjectSettings.has_setting(autoload_key) and _router.has_plugin():
		_router.remove_autoload_singleton("GameState")

	# Restore every setting the scaffold touched.
	for key in snapshot["settings"]:
		var state: Dictionary = snapshot["settings"][key]
		if state["had"]:
			ProjectSettings.set_setting(key, state["value"])
		else:
			ProjectSettings.set_setting(key, null)

	var save_err := ProjectSettings.save()
	if save_err != OK:
		# Last resort: put the original project.godot bytes back on disk.
		var project_text := str(snapshot["project_text"])
		if project_text.is_empty():
			errors.append("could not save project settings (error %d)" % save_err)
		else:
			var file := FileAccess.open(PROJECT_FILE, FileAccess.WRITE)
			if file == null:
				errors.append("could not restore project.godot (error %d)" % save_err)
			else:
				file.store_string(project_text)
				file.close()
				# The disk is authoritative again; drop the editor's stale view.
				EditorInterface.get_resource_filesystem().update_file(PROJECT_FILE)

	if errors.is_empty():
		return {"ok": true}
	return {"ok": false, "error": "; ".join(errors)}


func _apply_scaffold(
	type: String, project_name: String, main_scene_name: String, snapshot: Dictionary
) -> Dictionary:
	var paths_created: Array = []

	# 1. Directories
	for d in DIRS:
		var dir_err := _ensure_dir(d)
		if dir_err != OK:
			return _step_failed("create directory '%s'" % d, "error %d" % dir_err)
		if not snapshot["dirs"][d]:
			paths_created.append(d)

	# 2. Project settings (application name, display, rendering)
	ProjectSettings.set_setting("application/config/name", project_name)
	match type:
		"2d_platformer", "top_down_rpg", "visual_novel":
			ProjectSettings.set_setting("display/window/size/viewport_width", 1280)
			ProjectSettings.set_setting("display/window/size/viewport_height", 720)
			ProjectSettings.set_setting("rendering/renderer/rendering_method", "gl_compatibility")
			ProjectSettings.set_setting("physics/2d/default_gravity", 980.0)
		"3d_fps":
			ProjectSettings.set_setting("display/window/size/viewport_width", 1920)
			ProjectSettings.set_setting("display/window/size/viewport_height", 1080)
			ProjectSettings.set_setting("rendering/renderer/rendering_method", "forward_plus")
			ProjectSettings.set_setting("physics/3d/default_gravity", 9.8)

	# 3. Autoload (empty script, registered through the editor API when available)
	var script_err := _write_script(GAME_STATE_SCRIPT, "extends Node\n")
	if script_err != OK:
		return _step_failed("write '%s'" % GAME_STATE_SCRIPT, "error %d" % script_err)
	if not snapshot["files"][GAME_STATE_SCRIPT]["existed"]:
		paths_created.append(GAME_STATE_SCRIPT)
	if _router.has_plugin():
		_router.add_autoload_singleton("GameState", GAME_STATE_SCRIPT)
	else:
		ProjectSettings.set_setting("autoload/GameState", "*" + GAME_STATE_SCRIPT)
	if not ProjectSettings.has_setting("autoload/GameState"):
		return _step_failed("register autoload 'GameState'", "the editor did not apply it")

	# 4. Root scene
	var main_scene_path := "res://scenes/%s.tscn" % main_scene_name
	var root: Node = null
	match type:
		"2d_platformer", "top_down_rpg", "visual_novel":
			root = Node2D.new()
		"3d_fps":
			root = Node3D.new()
	root.name = main_scene_name
	var scene_err := _write_packed_scene(root, main_scene_path)
	root.free()
	if scene_err != OK:
		return _step_failed("save main scene '%s'" % main_scene_path, "error %d" % scene_err)
	if not snapshot["files"][main_scene_path]["existed"]:
		paths_created.append(main_scene_path)

	# 5. Main scene + persist the whole settings transaction once
	ProjectSettings.set_setting("application/run/main_scene", main_scene_path)
	var save_err := ProjectSettings.save()
	if save_err != OK:
		return _step_failed("save project settings", "error %d" % save_err)

	return {
		"ok": true,
		"paths_created": paths_created,
		"autoloads_registered": ["GameState"],
	}


# -- handlers ----------------------------------------------------------------

func _cmd_scaffold_project(params: Dictionary) -> Dictionary:
	var type := str(params.get("type", ""))
	var project_name := str(params.get("project_name", type))
	var main_scene_name := str(params.get("main_scene", "main"))
	var confirm := bool(params.get("confirm", false))

	var supported: Array = ["2d_platformer", "3d_fps", "top_down_rpg", "visual_novel"]
	if not type in supported:
		return _router._fail("VALIDATION_ERROR", "Unknown scaffold type '%s'. Supported: %s." % [type, supported])

	if not confirm:
		return _router._fail("PRECONDITION_FAILED", "'scaffold_project' is destructive. Pass confirm=true to proceed.", "confirm")

	# Keep the generated scene inside scenes/ — an identifier cannot traverse.
	if not main_scene_name.is_valid_identifier():
		return _router._fail(
			"VALIDATION_ERROR",
			"'main_scene' must be a valid identifier (no slashes or '..').",
			"main_scene",
		)

	var main_scene_path := "res://scenes/%s.tscn" % main_scene_name
	var snapshot := _snapshot(main_scene_path)
	var outcome := _apply_scaffold(type, project_name, main_scene_name, snapshot)
	if outcome.get("ok", false):
		return _router._ok({
			"created": true,
			"paths_created": outcome["paths_created"],
			"autoloads_registered": outcome["autoloads_registered"],
		})

	var rollback := _rollback(snapshot)
	var hint := "Scaffold failed at %s: %s." % [
		outcome.get("step", "unknown step"), outcome.get("error", "unknown error")
	]
	if rollback.get("ok", false):
		hint += " All changes were rolled back."
	else:
		hint += " Rollback was incomplete: %s." % rollback.get("error", "unknown error")
	return _router._fail("INTERNAL_ERROR", hint)
