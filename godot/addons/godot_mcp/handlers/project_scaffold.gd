@tool
class_name MCPProjectScaffoldHandlers
extends RefCounted
## Domain handler: project scaffold (issue #112).
##
## Generates a project skeleton (directories, settings, autoloads, root scene)
## for common game types so agents start from a known structure.
##
## Registered by the router on _init().

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_scaffold_project"] = _cmd_scaffold_project


# -- helpers -----------------------------------------------------------------

func _ensure_dir(path: String) -> void:
	var abs := ProjectSettings.globalize_path(path)
	if not DirAccess.dir_exists_absolute(abs):
		DirAccess.make_dir_recursive_absolute(abs)


func _write_script(path: String, code: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(code)
		file.close()
		EditorInterface.get_resource_filesystem().update_file(path)


func _write_packed_scene(root: Node, path: String) -> int:
	var scene := PackedScene.new()
	var err := scene.pack(root)
	if err != OK:
		return err
	err = ResourceSaver.save(scene, path)
	if err == OK:
		EditorInterface.get_resource_filesystem().update_file(path)
	return err


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

	var paths_created: Array = []
	var autoloads_registered: Array = []

	# 1. Directories
	var dirs := ["res://scenes/", "res://scripts/", "res://assets/", "res://shaders/"]
	for d in dirs:
		_ensure_dir(d)
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
	ProjectSettings.save()
	paths_created.append("res://project.godot")

	# 3. Autoloads (empty scripts)
	var game_state_script := "res://scripts/game_state.gd"
	_write_script(game_state_script, "extends Node\n")
	paths_created.append(game_state_script)
	ProjectSettings.set_setting("autoload/GameState", "*" + game_state_script)
	autoloads_registered.append("GameState")
	ProjectSettings.save()

	# 4. Root scene
	var main_scene_path := "res://scenes/%s.tscn" % main_scene_name
	var root: Node
	match type:
		"2d_platformer", "top_down_rpg", "visual_novel":
			root = Node2D.new()
		"3d_fps":
			root = Node3D.new()
	root.name = main_scene_name

	var err := _write_packed_scene(root, main_scene_path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save main scene (error %d)." % err)
	paths_created.append(main_scene_path)

	# 5. Set main scene
	ProjectSettings.set_setting("application/run/main_scene", main_scene_path)
	ProjectSettings.save()

	return _router._ok({
		"created": true,
		"paths_created": paths_created,
		"autoloads_registered": autoloads_registered,
	})
