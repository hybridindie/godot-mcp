@tool
class_name MCPCommandRouter
extends RefCounted
## Routes incoming command envelopes to cmd_* handlers (issues #3, #5).
##
## Pure dispatch + structured errors; every outcome is a JSON-safe response
## envelope — { id, ok, result } or { id, ok:false, error, hint[, required] } —
## never a raw error or crash (see .claude/rules/error-handling.md).
##
## Handlers receive the params dict and return a response *body* (without id) via
## the _ok / _fail builders; handle() stamps the id. Read-only inspection
## handlers (#5) read editor state through EditorInterface; safety/preconditions
## are owned by the MCP server, except the local guards needed to return a
## structured error instead of crashing.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")

var _handlers: Dictionary = {}


func _init() -> void:
	# Wire command strings are the cmd_<verb>_<noun> handler names (the matching MCP
	# tool drops the cmd_ prefix); see docs/architecture.md.
	_handlers["cmd_ping"] = _cmd_ping
	_handlers["cmd_get_project_info"] = _cmd_get_project_info
	_handlers["cmd_get_active_scene"] = _cmd_get_active_scene
	_handlers["cmd_get_scene_tree"] = _cmd_get_scene_tree
	_handlers["cmd_get_selected_node"] = _cmd_get_selected_node
	_handlers["cmd_get_node_properties"] = _cmd_get_node_properties
	# Mutations (issue #6) — all UndoRedo-wrapped via EditorUndoRedoManager.
	_handlers["cmd_create_node"] = _cmd_create_node
	_handlers["cmd_rename_node"] = _cmd_rename_node
	_handlers["cmd_set_node_property"] = _cmd_set_node_property
	_handlers["cmd_delete_node"] = _cmd_delete_node
	_handlers["cmd_attach_script"] = _cmd_attach_script
	_handlers["cmd_connect_signal"] = _cmd_connect_signal
	_handlers["cmd_save_scene"] = _cmd_save_scene
	_handlers["cmd_create_scene"] = _cmd_create_scene
	# Script read/patch (issue #10).
	_handlers["cmd_read_script"] = _cmd_read_script
	_handlers["cmd_list_scripts"] = _cmd_list_scripts
	_handlers["cmd_get_script_for_node"] = _cmd_get_script_for_node
	_handlers["cmd_write_script"] = _cmd_write_script
	_handlers["cmd_patch_script"] = _cmd_patch_script
	# Node parity (issue #31) — all UndoRedo-wrapped.
	_handlers["cmd_duplicate_node"] = _cmd_duplicate_node
	_handlers["cmd_move_node"] = _cmd_move_node
	_handlers["cmd_add_to_group"] = _cmd_add_to_group
	_handlers["cmd_remove_from_group"] = _cmd_remove_from_group
	_handlers["cmd_list_signal_connections"] = _cmd_list_signal_connections
	_handlers["cmd_disconnect_signal"] = _cmd_disconnect_signal
	# Resource files + autoloads (issue #34).
	_handlers["cmd_read_resource"] = _cmd_read_resource
	_handlers["cmd_create_resource"] = _cmd_create_resource
	_handlers["cmd_set_resource_property"] = _cmd_set_resource_property
	_handlers["cmd_register_autoload"] = _cmd_register_autoload
	_handlers["cmd_unregister_autoload"] = _cmd_unregister_autoload
	# Project & filesystem (issue #32).
	_handlers["cmd_get_filesystem_tree"] = _cmd_get_filesystem_tree
	_handlers["cmd_search_files"] = _cmd_search_files
	_handlers["cmd_get_setting"] = _cmd_get_setting
	_handlers["cmd_set_setting"] = _cmd_set_setting
	_handlers["cmd_path_to_uid"] = _cmd_path_to_uid
	_handlers["cmd_uid_to_path"] = _cmd_uid_to_path
	# Editor screenshots (issue #33).
	_handlers["cmd_capture_editor_screenshot"] = _cmd_capture_editor_screenshot
	# Physics (issue #41) — all UndoRedo-wrapped.
	_handlers["cmd_setup_physics_body"] = _cmd_setup_physics_body
	_handlers["cmd_setup_collision"] = _cmd_setup_collision
	_handlers["cmd_set_physics_layers"] = _cmd_set_physics_layers
	_handlers["cmd_add_raycast"] = _cmd_add_raycast
	# Animation (issue #39) — all UndoRedo-wrapped.
	_handlers["cmd_create_animation"] = _cmd_create_animation
	_handlers["cmd_add_animation_track"] = _cmd_add_animation_track
	_handlers["cmd_insert_keyframe"] = _cmd_insert_keyframe
	_handlers["cmd_create_animation_tree"] = _cmd_create_animation_tree
	_handlers["cmd_add_state_machine_state"] = _cmd_add_state_machine_state
	_handlers["cmd_set_blend_tree_node"] = _cmd_set_blend_tree_node
	# 3D scene (issue #40) — all UndoRedo-wrapped.
	_handlers["cmd_add_mesh_instance"] = _cmd_add_mesh_instance
	_handlers["cmd_setup_camera"] = _cmd_setup_camera
	_handlers["cmd_setup_lighting"] = _cmd_setup_lighting
	_handlers["cmd_setup_environment"] = _cmd_setup_environment
	_handlers["cmd_gridmap_set_cell"] = _cmd_gridmap_set_cell
	# Particles (issue #42) — all UndoRedo-wrapped.
	_handlers["cmd_create_particles"] = _cmd_create_particles
	_handlers["cmd_set_particle_material"] = _cmd_set_particle_material
	_handlers["cmd_set_particle_color_gradient"] = _cmd_set_particle_color_gradient
	_handlers["cmd_apply_particle_preset"] = _cmd_apply_particle_preset
	# Navigation (issue #43) — all UndoRedo-wrapped.
	_handlers["cmd_setup_navigation_region"] = _cmd_setup_navigation_region
	_handlers["cmd_setup_navigation_agent"] = _cmd_setup_navigation_agent
	_handlers["cmd_bake_navigation_mesh"] = _cmd_bake_navigation_mesh
	_handlers["cmd_set_navigation_layers"] = _cmd_set_navigation_layers
	# Audio (issue #44) — bus/effect mutations UndoRedo-wrapped; layout read is read-only.
	_handlers["cmd_add_audio_player"] = _cmd_add_audio_player
	_handlers["cmd_get_audio_bus_layout"] = _cmd_get_audio_bus_layout
	_handlers["cmd_add_audio_bus"] = _cmd_add_audio_bus
	_handlers["cmd_add_audio_bus_effect"] = _cmd_add_audio_bus_effect
	# TileMap (issue #45) — cell edits UndoRedo-wrapped; cell/layer reads are read-only.
	_handlers["cmd_tilemap_set_cell"] = _cmd_tilemap_set_cell
	_handlers["cmd_tilemap_fill_rect"] = _cmd_tilemap_fill_rect
	_handlers["cmd_tilemap_get_cell"] = _cmd_tilemap_get_cell
	_handlers["cmd_tilemap_clear"] = _cmd_tilemap_clear
	_handlers["cmd_tilemap_layers"] = _cmd_tilemap_layers
	# Theme & UI (issue #46) — all UndoRedo-wrapped.
	_handlers["cmd_create_theme"] = _cmd_create_theme
	_handlers["cmd_set_theme_color"] = _cmd_set_theme_color
	_handlers["cmd_set_theme_font_size"] = _cmd_set_theme_font_size
	_handlers["cmd_set_theme_stylebox"] = _cmd_set_theme_stylebox
	# Shaders (issue #47) — file/material edits UndoRedo-wrapped; shader read is read-only.
	_handlers["cmd_create_shader"] = _cmd_create_shader
	_handlers["cmd_read_shader"] = _cmd_read_shader
	_handlers["cmd_assign_shader_material"] = _cmd_assign_shader_material
	_handlers["cmd_set_shader_param"] = _cmd_set_shader_param


## Dispatch one envelope ({ id, command, params }) and return a response envelope.
func handle(envelope: Dictionary) -> Dictionary:
	var body := _route(envelope)
	body["id"] = str(envelope.get("id", ""))
	return body


func has_command(command: String) -> bool:
	return _handlers.has(command)


func _route(envelope: Dictionary) -> Dictionary:
	if not envelope.has("command"):
		return _fail("VALIDATION_ERROR", "Envelope is missing 'command'.")
	var command := str(envelope["command"])
	if not _handlers.has(command):
		return _fail("VALIDATION_ERROR", "Unknown command '%s'." % command)
	var raw_params: Variant = envelope.get("params", {})
	if typeof(raw_params) != TYPE_DICTIONARY:
		return _fail("VALIDATION_ERROR", "'params' must be an object.")
	var handler: Callable = _handlers[command]
	return handler.call(raw_params as Dictionary)


# --- handlers --------------------------------------------------------------

func _cmd_ping(_params: Dictionary) -> Dictionary:
	return _ok({"pong": true})


func _cmd_get_project_info(_params: Dictionary) -> Dictionary:
	return _ok({
		"name": ProjectSettings.get_setting("application/config/name", ""),
		"godot_version": Engine.get_version_info().get("string", ""),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"project_path": ProjectSettings.globalize_path("res://"),
		"autoloads": _autoloads(),
		"input_actions": _input_actions(),
	})


func _cmd_get_active_scene(_params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _ok({"is_open": false, "path": null, "name": null})
	return _ok({"is_open": true, "path": root.scene_file_path, "name": _scene_name(root)})


func _cmd_get_scene_tree(params: Dictionary) -> Dictionary:
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _ok({"tree": null})
	var max_depth := int(params.get("max_depth", -1))
	return _ok({"tree": Inspect.serialize_tree(root, max_depth)})


func _cmd_get_selected_node(_params: Dictionary) -> Dictionary:
	var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
	if selected.is_empty():
		return _ok({"selected": null})
	var root: Node = EditorInterface.get_edited_scene_root()
	return _ok({"selected": Inspect.node_info(selected[0], root if root != null else selected[0])})


func _cmd_get_node_properties(params: Dictionary) -> Dictionary:
	if not params.has("node_path"):
		return _fail("VALIDATION_ERROR", "'node_path' is required.")
	var root: Node = EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node: Node = root.get_node_or_null(NodePath(str(params["node_path"])))
	if node == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params["node_path"]))
	return _ok(Inspect.node_info(node, root))


# --- mutation handlers (issue #6) ------------------------------------------

func _cmd_create_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_type := str(params.get("node_type", ""))
	if not ClassDB.class_exists(node_type) or not ClassDB.can_instantiate(node_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable node type '%s'." % node_type)
	var parent: Node = root.get_node_or_null(NodePath(str(params.get("parent_path", "."))))
	if parent == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(params.get("parent_path")))

	var node: Node = ClassDB.instantiate(node_type)
	node.name = str(params.get("name", node_type))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create %s" % node.name)
	ur.add_do_method(parent, "add_child", node)
	ur.add_do_method(node, "set_owner", root)
	ur.add_do_reference(node)
	ur.add_undo_method(parent, "remove_child", node)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(node, root), "created": true})


func _cmd_rename_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var old_name := String(node.name)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Rename %s" % old_name)
	ur.add_do_property(node, "name", str(params.get("new_name", old_name)))
	ur.add_undo_property(node, "name", old_name)
	ur.commit_action()
	return _ok({
		"node_path": Inspect.relative_path(node, EditorInterface.get_edited_scene_root()),
		"old_name": old_name,
		"new_name": String(node.name),
		"renamed": true,
	})


func _cmd_set_node_property(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var property := str(params.get("property", ""))
	var prop_type := _property_type(node, property)
	if prop_type == -1:
		return _fail("VALIDATION_ERROR", "Node has no property '%s'." % property)

	var old_value: Variant = node.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [String(node.name), property])
	ur.add_do_property(node, property, new_value)
	ur.add_undo_property(node, property, old_value)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"property": property,
		"value": Coerce.to_json(node.get(property)),
		"set": true,
	})


func _cmd_delete_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if node == root:
		return _fail("VALIDATION_ERROR", "Cannot delete the scene root.")
	# Server enforces the safety class; the addon honors the confirm flag too.
	if not bool(params.get("confirm", false)):
		return _fail("PRECONDITION_FAILED", "Deleting a node requires confirm=true.", "confirm")

	var parent := node.get_parent()
	var index := node.get_index()  # restore at the same sibling position on undo
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Delete %s" % node.name)
	ur.add_do_method(parent, "remove_child", node)
	ur.add_undo_method(parent, "add_child", node)
	ur.add_undo_method(parent, "move_child", node, index)
	ur.add_undo_method(node, "set_owner", root)
	ur.add_undo_reference(node)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "deleted": true})


func _cmd_attach_script(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var script_path := str(params.get("script_path", ""))
	if not ResourceLoader.exists(script_path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'. Create it first." % script_path)
	var script: Variant = load(script_path)
	if not (script is Script):
		return _fail("VALIDATION_ERROR", "'%s' is not a script resource." % script_path)

	var old_script: Variant = node.get_script()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Attach script to %s" % node.name)
	ur.add_do_method(node, "set_script", script)
	ur.add_undo_method(node, "set_script", old_script)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "script_path": script_path, "attached": true})


func _cmd_connect_signal(params: Dictionary) -> Dictionary:
	var source_found := _resolve(params.get("source_path", ""))
	if not source_found["ok"]:
		return source_found
	var target_found := _resolve(params.get("target_path", ""))
	if not target_found["ok"]:
		return target_found
	var source: Node = source_found["node"]
	var target: Node = target_found["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _fail("VALIDATION_ERROR", "Source has no signal '%s'." % signal_name)
	if not target.has_method(method_name):
		return _fail("VALIDATION_ERROR", "Target has no method '%s'." % method_name)
	var callable := Callable(target, method_name)
	if source.is_connected(signal_name, callable):
		return _fail("VALIDATION_ERROR", "Signal '%s' is already connected to that method." % signal_name)

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Connect %s" % signal_name)
	# CONNECT_PERSIST so the connection is saved into the scene file.
	ur.add_do_method(source, "connect", signal_name, callable, Object.CONNECT_PERSIST)
	ur.add_undo_method(source, "disconnect", signal_name, callable)
	ur.commit_action()
	return _ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"connected": true,
	})


func _cmd_save_scene(_params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	if root.scene_file_path.is_empty():
		return _fail("PRECONDITION_FAILED", "Scene has no path yet; create it with a path first.", "scene_path")
	var err := EditorInterface.save_scene()
	if err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save scene (error %d)." % err)
	return _ok({"path": root.scene_file_path, "saved": true})


func _cmd_create_scene(params: Dictionary) -> Dictionary:
	var root_type := str(params.get("root_type", ""))
	var scene_path := str(params.get("scene_path", ""))
	if not ClassDB.class_exists(root_type) or not ClassDB.can_instantiate(root_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable root type '%s'." % root_type)
	if not scene_path.ends_with(".tscn") and not scene_path.ends_with(".scn"):
		return _fail("VALIDATION_ERROR", "scene_path must end with .tscn or .scn.")

	var root: Node = ClassDB.instantiate(root_type)
	root.name = scene_path.get_file().get_basename()
	var packed := PackedScene.new()
	var pack_err := packed.pack(root)
	root.free()
	if pack_err != OK:
		return _fail("INTERNAL_ERROR", "Failed to pack scene (error %d)." % pack_err)
	var save_err := ResourceSaver.save(packed, scene_path)
	if save_err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save scene to '%s' (error %d)." % [scene_path, save_err])
	# Creating a file isn't an UndoRedo-tracked tree edit; open it for editing.
	EditorInterface.open_scene_from_path(scene_path)
	return _ok({"scene_path": scene_path, "root_type": root_type, "created": true})


# --- script handlers (issue #10) -------------------------------------------

func _cmd_read_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must be a .gd file: '%s'." % path)
	if not FileAccess.file_exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	return _ok({"script_path": path, "content": FileAccess.get_file_as_string(path)})


func _cmd_list_scripts(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var scripts: Array = []
	_collect_gd(directory, scripts)
	scripts.sort()
	return _ok({"directory": directory, "scripts": scripts})


func _cmd_get_script_for_node(params: Dictionary) -> Dictionary:
	var raw := str(params.get("node_path", ""))
	var root := EditorInterface.get_edited_scene_root()
	var node: Node
	if raw.is_empty():
		var selected: Array[Node] = EditorInterface.get_selection().get_selected_nodes()
		if selected.is_empty():
			return _fail("PRECONDITION_FAILED", "No node_path given and nothing selected.", "node_or_selection")
		node = selected[0]
	else:
		if root == null:
			return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
		node = root.get_node_or_null(NodePath(raw))
		if node == null:
			return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % raw)
	# Always report the resolved scene-relative path so the response is self-describing.
	var resolved := Inspect.relative_path(node, root) if root != null else String(node.name)
	var script: Variant = node.get_script()
	if not (script is Script) or script.resource_path.is_empty():
		return _ok({"node_path": resolved, "script_path": null, "content": null})
	return _ok({
		"node_path": resolved,
		"script_path": script.resource_path,
		"content": FileAccess.get_file_as_string(script.resource_path),
	})


func _cmd_write_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must end with .gd.")
	var content := str(params.get("content", ""))
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Write script %s" % path)
	ur.add_do_method(self, "_write_file_text", path, content)
	if existed:
		ur.add_undo_method(self, "_write_file_text", path, old)
	else:
		ur.add_undo_method(self, "_remove_file", path)
	ur.commit_action()
	return _ok({"script_path": path, "created": not existed})


func _cmd_patch_script(params: Dictionary) -> Dictionary:
	var path := str(params.get("script_path", ""))
	if not path.ends_with(".gd"):
		return _fail("VALIDATION_ERROR", "script_path must end with .gd.")
	if not FileAccess.file_exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script at '%s'." % path)
	var find := str(params.get("find", ""))
	if find.is_empty():
		return _fail("VALIDATION_ERROR", "'find' must be a non-empty string.")
	var content := FileAccess.get_file_as_string(path)
	var occurrences := content.count(find)
	if occurrences == 0:
		return _fail("VALIDATION_ERROR", "'find' text was not found in the script.")
	var patched := content.replace(find, str(params.get("replace", "")))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Patch script %s" % path)
	ur.add_do_method(self, "_write_file_text", path, patched)
	ur.add_undo_method(self, "_write_file_text", path, content)
	ur.commit_action()
	return _ok({"script_path": path, "replacements": occurrences})


## Collect .gd files recursively under a res:// directory (skips hidden dirs).
func _collect_gd(directory: String, out: Array) -> void:
	var dir := DirAccess.open(directory)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := directory.path_join(name)
		if dir.current_is_dir():
			if not name.begins_with("."):
				_collect_gd(full, out)
		elif name.ends_with(".gd"):
			out.append(full)
		name = dir.get_next()
	dir.list_dir_end()


## Write text to a file (creating parent dirs) and tell the editor to re-import it.
## Used as the UndoRedo do/undo callback for script writes.
func _write_file_text(path: String, text: String) -> void:
	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(text)
		file.close()
	EditorInterface.get_resource_filesystem().update_file(path)


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
		EditorInterface.get_resource_filesystem().update_file(path)


# --- node parity handlers (issue #31) --------------------------------------

func _cmd_duplicate_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var parent := node.get_parent()
	if node == root or parent == null:
		return _fail("VALIDATION_ERROR", "Cannot duplicate the scene root.")

	var dup := node.duplicate()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Duplicate %s" % node.name)
	# force_readable_name=true so a name collision becomes "Box2", not "@Box@123".
	ur.add_do_method(parent, "add_child", dup, true)
	ur.add_do_method(self, "_own_recursive", dup, root)
	ur.add_do_reference(dup)
	ur.add_undo_method(parent, "remove_child", dup)
	ur.commit_action()
	return _ok({
		"node_path": Inspect.relative_path(dup, root),
		"source_path": str(params.get("node_path")),
	})


func _cmd_move_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var old_parent := node.get_parent()
	if node == root or old_parent == null:
		return _fail("VALIDATION_ERROR", "Cannot move the scene root.")
	var dest := _resolve(params.get("new_parent_path", ""))
	if not dest["ok"]:
		return dest
	var new_parent: Node = dest["node"]
	if new_parent == node or node.is_ancestor_of(new_parent):
		return _fail("VALIDATION_ERROR", "Cannot move a node into itself or one of its descendants.")

	var old_index := node.get_index()
	var index := int(params.get("index", -1))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Move %s" % node.name)
	ur.add_do_method(old_parent, "remove_child", node)
	ur.add_do_method(new_parent, "add_child", node)
	ur.add_do_method(self, "_own_recursive", node, root)
	if index >= 0:
		ur.add_do_method(new_parent, "move_child", node, index)
	ur.add_do_reference(node)
	ur.add_undo_method(new_parent, "remove_child", node)
	ur.add_undo_method(old_parent, "add_child", node)
	ur.add_undo_method(self, "_own_recursive", node, root)
	ur.add_undo_method(old_parent, "move_child", node, old_index)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(node, root), "moved": true})


func _cmd_add_to_group(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if node.is_in_group(group):
		return _ok({"node_path": str(params.get("node_path")), "group": group, "added": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s to group %s" % [node.name, group])
	# persistent=true so the membership is saved into the scene.
	ur.add_do_method(node, "add_to_group", group, true)
	ur.add_undo_method(node, "remove_from_group", group)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "group": group, "added": true})


func _cmd_remove_from_group(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var group := str(params.get("group", ""))
	if group.is_empty():
		return _fail("VALIDATION_ERROR", "'group' must be a non-empty string.")
	if not node.is_in_group(group):
		return _ok({"node_path": str(params.get("node_path")), "group": group, "removed": false})

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Remove %s from group %s" % [node.name, group])
	ur.add_do_method(node, "remove_from_group", group)
	ur.add_undo_method(node, "add_to_group", group, true)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "group": group, "removed": true})


func _cmd_list_signal_connections(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var connections: Array = []
	for sig in node.get_signal_list():
		var signal_name: String = sig["name"]
		for conn in node.get_signal_connection_list(signal_name):
			var callable: Callable = conn["callable"]
			var target: Object = callable.get_object()
			var target_path: String
			if target is Node and root != null:
				target_path = Inspect.relative_path(target, root)
			else:
				target_path = str(target)
			connections.append({
				"signal": signal_name,
				"target_path": target_path,
				"method": String(callable.get_method()),
				"persistent": (int(conn.get("flags", 0)) & Object.CONNECT_PERSIST) != 0,
			})
	return _ok({"node_path": str(params.get("node_path")), "connections": connections})


func _cmd_disconnect_signal(params: Dictionary) -> Dictionary:
	var src := _resolve(params.get("source_path", ""))
	if not src["ok"]:
		return src
	var tgt := _resolve(params.get("target_path", ""))
	if not tgt["ok"]:
		return tgt
	var source: Node = src["node"]
	var target: Node = tgt["node"]
	var signal_name := str(params.get("signal_name", ""))
	var method_name := str(params.get("method_name", ""))
	if not source.has_signal(signal_name):
		return _fail("VALIDATION_ERROR", "Source has no signal '%s'." % signal_name)
	if not target.has_method(method_name):
		return _fail("VALIDATION_ERROR", "Target has no method '%s'." % method_name)
	var callable := Callable(target, method_name)
	if not source.is_connected(signal_name, callable):
		return _fail("VALIDATION_ERROR", "Signal '%s' is not connected to that method." % signal_name)

	# Capture the original flags so undo restores the connection faithfully.
	var flags := 0
	for conn in source.get_signal_connection_list(signal_name):
		if (conn["callable"] as Callable) == callable:
			flags = int(conn["flags"])
			break
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Disconnect %s" % signal_name)
	ur.add_do_method(source, "disconnect", signal_name, callable)
	ur.add_undo_method(source, "connect", signal_name, callable, flags)
	ur.commit_action()
	return _ok({
		"source_path": str(params.get("source_path")),
		"signal_name": signal_name,
		"target_path": str(params.get("target_path")),
		"method_name": method_name,
		"disconnected": true,
	})


# --- animation (issue #39) -------------------------------------------------

const _TRACK_TYPES := {
	"value": Animation.TYPE_VALUE,
	"position_3d": Animation.TYPE_POSITION_3D,
	"rotation_3d": Animation.TYPE_ROTATION_3D,
	"scale_3d": Animation.TYPE_SCALE_3D,
	"method": Animation.TYPE_METHOD,
	"bezier": Animation.TYPE_BEZIER,
	"audio": Animation.TYPE_AUDIO,
	"animation": Animation.TYPE_ANIMATION,
}


func _cmd_create_animation(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var player: Node = found["node"]
	if not (player is AnimationPlayer):
		return _fail("VALIDATION_ERROR", "Node is not an AnimationPlayer.")
	var anim_name := str(params.get("name", ""))
	if anim_name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")

	var created_lib := false
	var library: AnimationLibrary
	if player.has_animation_library(""):
		library = player.get_animation_library("")
	else:
		library = AnimationLibrary.new()
		created_lib = true
	if library.has_animation(anim_name):
		return _fail("VALIDATION_ERROR", "Animation '%s' already exists." % anim_name)

	var animation := Animation.new()
	animation.length = float(params.get("length", 1.0))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create animation %s" % anim_name)
	if created_lib:
		ur.add_do_method(player, "add_animation_library", "", library)
		ur.add_do_reference(library)
	ur.add_do_method(library, "add_animation", anim_name, animation)
	ur.add_do_reference(animation)
	ur.add_undo_method(library, "remove_animation", anim_name)
	if created_lib:
		ur.add_undo_method(player, "remove_animation_library", "")
	ur.commit_action()
	return _ok({"player_path": str(params.get("node_path")), "animation": anim_name, "length": animation.length})


func _cmd_add_animation_track(params: Dictionary) -> Dictionary:
	var found := _resolve_player_animation(params)
	if not found["ok"]:
		return found
	var animation: Animation = found["animation"]
	var track_type_key := str(params.get("track_type", "value"))
	if not _TRACK_TYPES.has(track_type_key):
		return _fail("VALIDATION_ERROR", "Unknown track_type '%s'." % track_type_key)
	var track_type: int = _TRACK_TYPES[track_type_key]
	var track_path := str(params.get("track_path", ""))
	if track_path.is_empty():
		return _fail("VALIDATION_ERROR", "'track_path' must be a non-empty string.")
	var index := animation.get_track_count()  # add_track appends to this index
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add animation track")
	ur.add_do_method(animation, "add_track", track_type, -1)
	ur.add_do_method(animation, "track_set_path", index, NodePath(track_path))
	ur.add_undo_method(animation, "remove_track", index)
	ur.commit_action()
	return _ok({"animation": str(params.get("animation")), "track": index, "track_path": track_path})


func _cmd_insert_keyframe(params: Dictionary) -> Dictionary:
	var found := _resolve_player_animation(params)
	if not found["ok"]:
		return found
	var animation: Animation = found["animation"]
	var track := int(params.get("track", -1))
	if track < 0 or track >= animation.get_track_count():
		return _fail("VALIDATION_ERROR", "Track %d is out of range." % track)
	var time := float(params.get("time", 0.0))
	var easing := float(params.get("easing", 1.0))
	var value: Variant = params.get("value")
	if value is String:  # accept string forms like "Vector2(10, 20)" (issue #51)
		var parsed: Variant = str_to_var(value)
		if parsed != null:
			value = parsed
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Insert keyframe")
	ur.add_do_method(animation, "track_insert_key", track, time, value, easing)
	ur.add_undo_method(animation, "track_remove_key_at_time", track, time)
	ur.commit_action()
	return _ok({"animation": str(params.get("animation")), "track": track, "time": time})


func _cmd_create_animation_tree(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var root_type := str(params.get("root_type", "AnimationNodeStateMachine"))
	if not ClassDB.can_instantiate(root_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % root_type)
	var tree_root_obj: Object = ClassDB.instantiate(root_type)
	if not (tree_root_obj is AnimationRootNode):
		if not (tree_root_obj is RefCounted):
			tree_root_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not an AnimationRootNode." % root_type)

	var tree := AnimationTree.new()
	tree.name = str(params.get("name", "AnimationTree"))
	tree.tree_root = tree_root_obj
	if params.get("anim_player") != null:
		tree.anim_player = NodePath(str(params["anim_player"]))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create AnimationTree %s" % tree.name)
	ur.add_do_method(parent, "add_child", tree)
	ur.add_do_method(tree, "set_owner", root)
	ur.add_do_reference(tree)
	ur.add_undo_method(parent, "remove_child", tree)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(tree, root), "root_type": root_type})


func _cmd_add_state_machine_state(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("tree_path", ""))
	if not found["ok"]:
		return found
	var tree: Node = found["node"]
	if not (tree is AnimationTree) or not (tree.tree_root is AnimationNodeStateMachine):
		return _fail("VALIDATION_ERROR", "Node is not an AnimationTree with a state-machine root.")
	var state_machine: AnimationNodeStateMachine = tree.tree_root
	var state_name := str(params.get("state_name", ""))
	if state_name.is_empty():
		return _fail("VALIDATION_ERROR", "'state_name' must be a non-empty string.")
	var state := AnimationNodeAnimation.new()
	if params.get("animation") != null:
		state.animation = StringName(str(params["animation"]))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add state %s" % state_name)
	ur.add_do_method(state_machine, "add_node", state_name, state, Vector2.ZERO)
	ur.add_do_reference(state)
	ur.add_undo_method(state_machine, "remove_node", state_name)
	ur.commit_action()
	return _ok({"tree_path": str(params.get("tree_path")), "state": state_name})


func _cmd_set_blend_tree_node(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("tree_path", ""))
	if not found["ok"]:
		return found
	var tree: Node = found["node"]
	if not (tree is AnimationTree) or not (tree.tree_root is AnimationNodeBlendTree):
		return _fail("VALIDATION_ERROR", "Node is not an AnimationTree with a blend-tree root.")
	var blend_tree: AnimationNodeBlendTree = tree.tree_root
	var node_name := str(params.get("node_name", ""))
	if node_name.is_empty():
		return _fail("VALIDATION_ERROR", "'node_name' must be a non-empty string.")
	var node_type := str(params.get("node_type", ""))
	if not ClassDB.can_instantiate(node_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % node_type)
	var anim_node_obj: Object = ClassDB.instantiate(node_type)
	if not (anim_node_obj is AnimationNode):
		if not (anim_node_obj is RefCounted):
			anim_node_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not an AnimationNode." % node_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add blend-tree node %s" % node_name)
	ur.add_do_method(blend_tree, "add_node", node_name, anim_node_obj, Vector2.ZERO)
	ur.add_do_reference(anim_node_obj)
	ur.add_undo_method(blend_tree, "remove_node", node_name)
	ur.commit_action()
	return _ok({"tree_path": str(params.get("tree_path")), "node": node_name, "node_type": node_type})


## Resolve {ok, animation} for the AnimationPlayer at params.node_path and its
## animation named params.animation. Propagates _resolve's structured
## PRECONDITION_FAILED / RESOURCE_NOT_FOUND envelope rather than collapsing it.
func _resolve_player_animation(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var player: Node = found["node"]
	if not (player is AnimationPlayer):
		return _fail("VALIDATION_ERROR", "Node is not an AnimationPlayer.")
	var anim_name := str(params.get("animation", ""))
	if not player.has_animation(anim_name):
		return _fail("RESOURCE_NOT_FOUND", "No animation '%s' on the AnimationPlayer." % anim_name)
	return {"ok": true, "animation": player.get_animation(anim_name)}


# --- physics (issue #41) ---------------------------------------------------

func _cmd_setup_physics_body(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is CollisionObject2D or node is CollisionObject3D):
		return _fail("VALIDATION_ERROR", "Node is not a physics body/area (CollisionObject2D/3D).")
	var properties: Dictionary = params.get("properties", {})
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Configure body %s" % node.name)
	for key in properties:
		var prop_type := _property_type(node, str(key))
		if prop_type == -1:
			continue
		ur.add_do_property(node, str(key), Coerce.from_json(properties[key], prop_type))
		ur.add_undo_property(node, str(key), node.get(str(key)))
	ur.commit_action()
	var applied: Dictionary = {}
	for key in properties:
		if _property_type(node, str(key)) != -1:
			applied[str(key)] = Coerce.to_json(node.get(str(key)))
	return _ok({"node_path": str(params.get("node_path")), "properties": applied})


func _cmd_setup_collision(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	if not (parent is CollisionObject2D or parent is CollisionObject3D):
		return _fail("VALIDATION_ERROR", "Target is not a physics body/area (CollisionObject2D/3D).")
	var root := EditorInterface.get_edited_scene_root()
	var collision_node_type := str(params.get("collision_node_type", "CollisionShape2D"))
	var shape_type := str(params.get("shape_type", ""))
	if not ClassDB.can_instantiate(collision_node_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % collision_node_type)
	if not ClassDB.can_instantiate(shape_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate shape '%s'." % shape_type)

	var shape_obj: Object = ClassDB.instantiate(shape_type)
	if not (shape_obj is Shape2D or shape_obj is Shape3D):
		if not (shape_obj is RefCounted):
			shape_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a Shape2D/Shape3D." % shape_type)
	var shape: Resource = shape_obj
	var shape_props: Dictionary = params.get("properties", {})
	for key in shape_props:
		var pt := _property_type(shape, str(key))
		if pt != -1:
			shape.set(str(key), Coerce.from_json(shape_props[key], pt))

	var collision: Node = ClassDB.instantiate(collision_node_type)
	if not (collision is CollisionShape2D or collision is CollisionShape3D):
		collision.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a CollisionShape2D/3D." % collision_node_type)
	collision.name = str(params.get("name", collision_node_type))
	collision.set("shape", shape)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add collision shape to %s" % parent.name)
	ur.add_do_method(parent, "add_child", collision)
	ur.add_do_method(collision, "set_owner", root)
	ur.add_do_reference(collision)
	ur.add_undo_method(parent, "remove_child", collision)
	ur.commit_action()
	return _ok({
		"node_path": Inspect.relative_path(collision, root),
		"shape_type": shape_type,
		"created": true,
	})


func _cmd_set_physics_layers(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is CollisionObject2D or node is CollisionObject3D):
		return _fail("VALIDATION_ERROR", "Node is not a physics body/area (CollisionObject2D/3D).")
	if params.get("layers") != null and not _valid_bits(params["layers"]):
		return _fail("VALIDATION_ERROR", "'layers' must be an array of bit indices in [1, 32].")
	if params.get("mask") != null and not _valid_bits(params["mask"]):
		return _fail("VALIDATION_ERROR", "'mask' must be an array of bit indices in [1, 32].")
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set physics layers on %s" % node.name)
	if params.get("layers") != null:
		ur.add_do_property(node, "collision_layer", _bitmask(params["layers"]))
		ur.add_undo_property(node, "collision_layer", node.collision_layer)
	if params.get("mask") != null:
		ur.add_do_property(node, "collision_mask", _bitmask(params["mask"]))
		ur.add_undo_property(node, "collision_mask", node.collision_mask)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"collision_layer": node.collision_layer,
		"collision_mask": node.collision_mask,
	})


func _cmd_add_raycast(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var root := EditorInterface.get_edited_scene_root()
	var raycast_type := str(params.get("raycast_type", "RayCast2D"))
	if not ClassDB.can_instantiate(raycast_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % raycast_type)

	var ray: Node = ClassDB.instantiate(raycast_type)
	if not (ray is RayCast2D or ray is RayCast3D):
		ray.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a RayCast2D/RayCast3D." % raycast_type)
	ray.name = str(params.get("name", raycast_type))
	var ray_props: Dictionary = params.get("properties", {})
	for key in ray_props:
		var pt := _property_type(ray, str(key))
		if pt != -1:
			ray.set(str(key), Coerce.from_json(ray_props[key], pt))

	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s" % ray.name)
	ur.add_do_method(parent, "add_child", ray)
	ur.add_do_method(ray, "set_owner", root)
	ur.add_do_reference(ray)
	ur.add_undo_method(parent, "remove_child", ray)
	ur.commit_action()
	return _ok({"node_path": Inspect.relative_path(ray, root), "created": true})


## True if value is an array of 1-based bit indices, each in [1, 32].
func _valid_bits(value: Variant) -> bool:
	if not (value is Array):
		return false
	for bit in value:
		if typeof(bit) not in [TYPE_INT, TYPE_FLOAT]:
			return false
		var index := int(bit)
		if index < 1 or index > 32:
			return false
	return true


## Convert an array of 1-based bit indices into a collision-layer/mask integer.
func _bitmask(bits: Variant) -> int:
	var mask := 0
	if bits is Array:
		for bit in bits:
			var index := int(bit)
			if index >= 1 and index <= 32:
				mask |= 1 << (index - 1)
	return mask


# --- 3D scene (issue #40) --------------------------------------------------

func _cmd_add_mesh_instance(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var mesh_type := str(params.get("mesh_type", "BoxMesh"))
	if not ClassDB.can_instantiate(mesh_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate mesh '%s'." % mesh_type)
	var mesh_obj: Object = ClassDB.instantiate(mesh_type)
	if not (mesh_obj is Mesh):
		if not (mesh_obj is RefCounted):
			mesh_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a Mesh." % mesh_type)
	var mesh: Mesh = mesh_obj
	_apply_props(mesh, params.get("properties", {}))
	var instance := MeshInstance3D.new()
	instance.name = str(params.get("name", "MeshInstance3D"))
	instance.mesh = mesh
	var path := _commit_add_child(parent, instance, "Add %s" % instance.name)
	return _ok({"node_path": path, "mesh_type": mesh_type, "created": true})


func _cmd_setup_camera(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var camera := Camera3D.new()
	camera.name = str(params.get("name", "Camera3D"))
	_apply_props(camera, params.get("properties", {}))
	var make_current := bool(params.get("make_current", true))
	camera.current = make_current
	var path := _commit_add_child(parent, camera, "Add %s" % camera.name)
	return _ok({"node_path": path, "current": make_current, "created": true})


func _cmd_setup_lighting(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var light_type := str(params.get("light_type", "DirectionalLight3D"))
	if not ClassDB.can_instantiate(light_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % light_type)
	var light_obj: Object = ClassDB.instantiate(light_type)
	if not (light_obj is Light3D):
		if not (light_obj is RefCounted):
			light_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a Light3D." % light_type)
	var light: Light3D = light_obj
	light.name = str(params.get("name", light_type))
	_apply_props(light, params.get("properties", {}))
	var path := _commit_add_child(parent, light, "Add %s" % light.name)
	return _ok({"node_path": path, "light_type": light_type, "created": true})


func _cmd_setup_environment(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var world_env := WorldEnvironment.new()
	world_env.name = str(params.get("name", "WorldEnvironment"))
	var environment := Environment.new()
	_apply_props(environment, params.get("properties", {}))
	world_env.environment = environment
	var path := _commit_add_child(parent, world_env, "Add %s" % world_env.name)
	return _ok({"node_path": path, "created": true})


func _cmd_gridmap_set_cell(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is GridMap):
		return _fail("VALIDATION_ERROR", "Node is not a GridMap.")
	var grid_map: GridMap = node
	if grid_map.mesh_library == null:
		return _fail("VALIDATION_ERROR", "GridMap has no mesh_library; assign one first.", "mesh_library")
	var raw_pos: Variant = params.get("position")
	if not (raw_pos is Array) or (raw_pos as Array).size() != 3:
		return _fail("VALIDATION_ERROR", "'position' must be a [x, y, z] integer array.")
	var position := Vector3i(int(raw_pos[0]), int(raw_pos[1]), int(raw_pos[2]))
	var item := int(params.get("item", -1))
	var orientation := int(params.get("orientation", 0))
	var prev_item := grid_map.get_cell_item(position)
	var prev_orientation := grid_map.get_cell_item_orientation(position)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set GridMap cell %v" % position)
	ur.add_do_method(grid_map, "set_cell_item", position, item, orientation)
	ur.add_undo_method(grid_map, "set_cell_item", position, prev_item, prev_orientation)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"position": [position.x, position.y, position.z],
		"item": item,
	})


## Apply JSON properties to an object, coercing each value to the property's type.
## Unknown properties are skipped. Used for freshly-created (not-yet-in-tree) nodes,
## where the whole add is one undoable action.
func _apply_props(obj: Object, props: Dictionary) -> void:
	for key in props:
		var pt := _property_type(obj, str(key))
		if pt != -1:
			obj.set(str(key), Coerce.from_json(props[key], pt))


## Add `child` under `parent` as one undoable action; return its scene-relative path.
func _commit_add_child(parent: Node, child: Node, action_name: String) -> String:
	var root := EditorInterface.get_edited_scene_root()
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action(action_name)
	ur.add_do_method(parent, "add_child", child)
	ur.add_do_method(child, "set_owner", root)
	ur.add_do_reference(child)
	ur.add_undo_method(parent, "remove_child", child)
	ur.commit_action()
	return Inspect.relative_path(child, root)


# --- particles (issue #42) -------------------------------------------------

## Generic VFX presets: node + ParticleProcessMaterial properties + a color ramp.
## Vectors are dicts {x,y,z}; colors are HTML strings (RRGGBBAA). No game vocabulary.
const _PARTICLE_PRESETS := {
	"fire": {
		"node": {"amount": 32, "lifetime": 1.0, "explosiveness": 0.1},
		"material": {
			"direction": {"x": 0, "y": -1, "z": 0}, "spread": 20.0,
			"gravity": {"x": 0, "y": -30, "z": 0},
			"initial_velocity_min": 30.0, "initial_velocity_max": 60.0,
			"scale_min": 1.5, "scale_max": 3.0, "color": "#ffcc33",
		},
		"gradient": ["#ffee88ff", "#ff6600cc", "#cc220000"],
	},
	"smoke": {
		"node": {"amount": 24, "lifetime": 2.5, "explosiveness": 0.0},
		"material": {
			"direction": {"x": 0, "y": -1, "z": 0}, "spread": 12.0,
			"gravity": {"x": 0, "y": -8, "z": 0},
			"initial_velocity_min": 8.0, "initial_velocity_max": 18.0,
			"scale_min": 2.0, "scale_max": 5.0, "color": "#888888",
		},
		"gradient": ["#aaaaaaaa", "#66666666", "#33333300"],
	},
	"explosion": {
		"node": {"amount": 48, "lifetime": 0.8, "one_shot": true, "explosiveness": 1.0},
		"material": {
			"spread": 180.0, "gravity": {"x": 0, "y": 0, "z": 0},
			"initial_velocity_min": 60.0, "initial_velocity_max": 140.0,
			"scale_min": 1.0, "scale_max": 2.5, "color": "#ffaa33",
			"damping_min": 20.0, "damping_max": 40.0,
		},
		"gradient": ["#ffffccff", "#ff8800cc", "#88110000"],
	},
	"sparks": {
		"node": {"amount": 24, "lifetime": 0.6, "explosiveness": 0.4},
		"material": {
			"spread": 45.0, "gravity": {"x": 0, "y": 60, "z": 0},
			"initial_velocity_min": 40.0, "initial_velocity_max": 90.0,
			"scale_min": 0.4, "scale_max": 1.0, "color": "#ffee99",
		},
		"gradient": ["#ffffddff", "#ffcc33ff", "#ff660000"],
	},
}


func _cmd_create_particles(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var particles_type := str(params.get("particles_type", "GPUParticles2D"))
	if particles_type != "GPUParticles2D" and particles_type != "GPUParticles3D":
		return _fail("VALIDATION_ERROR", "particles_type must be GPUParticles2D or GPUParticles3D.")
	var particles := ClassDB.instantiate(particles_type) as Node
	if particles == null:
		return _fail("VALIDATION_ERROR", "Could not instantiate '%s'." % particles_type)
	particles.name = str(params.get("name", particles_type))
	particles.set("amount", maxi(1, int(params.get("amount", 8))))
	particles.set("lifetime", maxf(0.01, float(params.get("lifetime", 1.0))))
	particles.set("process_material", ParticleProcessMaterial.new())
	_apply_props(particles, params.get("properties", {}))
	var path := _commit_add_child(parent, particles, "Add %s" % particles.name)
	return _ok({"node_path": path, "particles_type": particles_type, "created": true})


func _cmd_set_particle_material(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var properties: Dictionary = params.get("properties", {})
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Configure particle material")
	var material := _stage_process_material(node, ur)
	for key in properties:
		var pt := _property_type(material, str(key))
		if pt != -1:
			ur.add_do_property(material, str(key), Coerce.from_json(properties[key], pt))
			ur.add_undo_property(material, str(key), material.get(str(key)))
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "properties": _applied_props(material, properties)})


func _cmd_set_particle_color_gradient(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var raw_colors: Variant = params.get("colors")
	if not (raw_colors is Array) or (raw_colors as Array).is_empty():
		return _fail("VALIDATION_ERROR", "'colors' must be a non-empty array of color stops.")
	var texture := _build_gradient_texture(raw_colors, params.get("offsets"))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set particle color gradient")
	var material := _stage_process_material(node, ur)
	ur.add_do_property(material, "color_ramp", texture)
	ur.add_do_reference(texture)
	ur.add_undo_property(material, "color_ramp", material.color_ramp)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "stops": (raw_colors as Array).size()})


func _cmd_apply_particle_preset(params: Dictionary) -> Dictionary:
	var found := _resolve_particles(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var preset_name := str(params.get("preset", ""))
	if not _PARTICLE_PRESETS.has(preset_name):
		return _fail("VALIDATION_ERROR", "Unknown preset '%s'." % preset_name)
	var preset: Dictionary = _PARTICLE_PRESETS[preset_name]
	var node_props: Dictionary = preset.get("node", {})
	var mat_props: Dictionary = preset.get("material", {})
	var grad_colors: Array = preset.get("gradient", [])
	var material := ParticleProcessMaterial.new()
	_apply_props(material, mat_props)
	if not grad_colors.is_empty():
		material.color_ramp = _build_gradient_texture(grad_colors, null)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Apply particle preset %s" % preset_name)
	ur.add_do_property(node, "process_material", material)
	ur.add_do_reference(material)
	ur.add_undo_property(node, "process_material", node.process_material)
	for key in node_props:
		var pt := _property_type(node, str(key))
		if pt != -1:
			ur.add_do_property(node, str(key), Coerce.from_json(node_props[key], pt))
			ur.add_undo_property(node, str(key), node.get(str(key)))
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "preset": preset_name})


## Resolve {ok, node} for a GPUParticles2D/3D node, preserving _resolve's envelope.
func _resolve_particles(raw_path: Variant) -> Dictionary:
	var found := _resolve(raw_path)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is GPUParticles2D or node is GPUParticles3D):
		return _fail("VALIDATION_ERROR", "Node is not a GPUParticles2D/GPUParticles3D.")
	return {"ok": true, "node": node}


## Return the node's ParticleProcessMaterial, queueing a fresh one on the UndoRedo
## action if absent (so material edits are part of the same undoable step).
func _stage_process_material(node: Node, ur: EditorUndoRedoManager) -> ParticleProcessMaterial:
	var existing: Variant = node.process_material
	if existing is ParticleProcessMaterial:
		return existing
	var material := ParticleProcessMaterial.new()
	ur.add_do_property(node, "process_material", material)
	ur.add_do_reference(material)
	ur.add_undo_property(node, "process_material", existing)
	return material


## Build a GradientTexture1D from an array of color stops and optional 0..1 offsets
## (evenly spaced when omitted/mismatched). Colors accept HTML strings or [r,g,b,a].
func _build_gradient_texture(raw_colors: Array, raw_offsets: Variant) -> GradientTexture1D:
	var colors := PackedColorArray()
	for c in raw_colors:
		colors.append(Coerce.from_json(c, TYPE_COLOR))
	var count := colors.size()
	var offsets := PackedFloat32Array()
	if raw_offsets is Array and (raw_offsets as Array).size() == count:
		for o in raw_offsets:
			offsets.append(clampf(float(o), 0.0, 1.0))
	else:
		for i in count:
			offsets.append(0.0 if count <= 1 else float(i) / float(count - 1))
	var gradient := Gradient.new()
	gradient.offsets = offsets
	gradient.colors = colors
	var texture := GradientTexture1D.new()
	texture.gradient = gradient
	return texture


## JSON-safe snapshot of the props actually present on an object (post-mutation).
func _applied_props(obj: Object, props: Dictionary) -> Dictionary:
	var applied: Dictionary = {}
	for key in props:
		if _property_type(obj, str(key)) != -1:
			applied[str(key)] = Coerce.to_json(obj.get(str(key)))
	return applied


# --- navigation (issue #43) ------------------------------------------------

func _cmd_setup_navigation_region(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var region_type := str(params.get("region_type", "NavigationRegion2D"))
	if region_type != "NavigationRegion2D" and region_type != "NavigationRegion3D":
		return _fail("VALIDATION_ERROR", "region_type must be NavigationRegion2D or NavigationRegion3D.")
	var region := ClassDB.instantiate(region_type) as Node
	if region == null:
		return _fail("VALIDATION_ERROR", "Could not instantiate '%s'." % region_type)
	region.name = str(params.get("name", region_type))
	# Assign an empty navmesh resource so the region is ready to bake.
	if region is NavigationRegion2D:
		region.navigation_polygon = NavigationPolygon.new()
	else:
		region.navigation_mesh = NavigationMesh.new()
	_apply_props(region, params.get("properties", {}))
	var path := _commit_add_child(parent, region, "Add %s" % region.name)
	return _ok({"node_path": path, "region_type": region_type, "created": true})


func _cmd_setup_navigation_agent(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var agent_type := str(params.get("agent_type", "NavigationAgent2D"))
	if agent_type != "NavigationAgent2D" and agent_type != "NavigationAgent3D":
		return _fail("VALIDATION_ERROR", "agent_type must be NavigationAgent2D or NavigationAgent3D.")
	var agent := ClassDB.instantiate(agent_type) as Node
	if agent == null:
		return _fail("VALIDATION_ERROR", "Could not instantiate '%s'." % agent_type)
	agent.name = str(params.get("name", agent_type))
	_apply_props(agent, params.get("properties", {}))
	var path := _commit_add_child(parent, agent, "Add %s" % agent.name)
	return _ok({"node_path": path, "agent_type": agent_type, "created": true})


func _cmd_bake_navigation_mesh(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var region: Node = found["node"]
	var ur := EditorInterface.get_editor_undo_redo()
	# Baking mutates the assigned navmesh resource in place. To stay undoable we bake a
	# fresh duplicate (the do/redo target) and keep the original pristine as the undo
	# value, so the snapshot is never the bake target and repeated undo/redo is stable.
	if region is NavigationRegion2D:
		if region.navigation_polygon == null:
			return _fail("VALIDATION_ERROR", "Region has no navigation_polygon; assign one first.", "navigation_polygon")
		var original: NavigationPolygon = region.navigation_polygon
		var working: NavigationPolygon = original.duplicate(true)
		ur.create_action("Bake navigation polygon")
		ur.add_do_property(region, "navigation_polygon", working)
		ur.add_do_method(region, "bake_navigation_polygon", false)
		ur.add_do_reference(working)
		ur.add_undo_property(region, "navigation_polygon", original)
		ur.add_undo_reference(original)
		ur.commit_action()
	elif region is NavigationRegion3D:
		if region.navigation_mesh == null:
			return _fail("VALIDATION_ERROR", "Region has no navigation_mesh; assign one first.", "navigation_mesh")
		var original: NavigationMesh = region.navigation_mesh
		var working: NavigationMesh = original.duplicate(true)
		ur.create_action("Bake navigation mesh")
		ur.add_do_property(region, "navigation_mesh", working)
		ur.add_do_method(region, "bake_navigation_mesh", false)
		ur.add_do_reference(working)
		ur.add_undo_property(region, "navigation_mesh", original)
		ur.add_undo_reference(original)
		ur.commit_action()
	else:
		return _fail("VALIDATION_ERROR", "Node is not a NavigationRegion2D/NavigationRegion3D.")
	return _ok({"node_path": str(params.get("node_path")), "baked": true})


func _cmd_set_navigation_layers(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if _property_type(node, "navigation_layers") == -1:
		return _fail("VALIDATION_ERROR", "Node has no 'navigation_layers' property.")
	if not _valid_bits(params.get("layers")):
		return _fail("VALIDATION_ERROR", "'layers' must be an array of bit indices in [1, 32].")
	var mask := _bitmask(params["layers"])
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set navigation layers on %s" % node.name)
	ur.add_do_property(node, "navigation_layers", mask)
	ur.add_undo_property(node, "navigation_layers", node.navigation_layers)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "navigation_layers": mask})


# --- audio (issue #44) -----------------------------------------------------

func _cmd_add_audio_player(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("parent_path", ""))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var player_type := str(params.get("player_type", "AudioStreamPlayer"))
	if player_type not in ["AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D"]:
		return _fail("VALIDATION_ERROR", "player_type must be an AudioStreamPlayer/2D/3D.")
	var player := ClassDB.instantiate(player_type) as Node
	if player == null:
		return _fail("VALIDATION_ERROR", "Could not instantiate '%s'." % player_type)
	player.name = str(params.get("name", player_type))
	var stream_path := str(params.get("stream_path", ""))
	if not stream_path.is_empty():
		if not ResourceLoader.exists(stream_path):
			return _fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % stream_path)
		var stream: Resource = ResourceLoader.load(stream_path)
		if not (stream is AudioStream):
			return _fail("VALIDATION_ERROR", "'%s' is not an AudioStream." % stream_path)
		player.set("stream", stream)
	_apply_props(player, params.get("properties", {}))
	var path := _commit_add_child(parent, player, "Add %s" % player.name)
	return _ok({"node_path": path, "player_type": player_type, "created": true})


func _cmd_get_audio_bus_layout(_params: Dictionary) -> Dictionary:
	var buses: Array = []
	for i in AudioServer.get_bus_count():
		var effects: Array = []
		for e in AudioServer.get_bus_effect_count(i):
			var effect := AudioServer.get_bus_effect(i, e)
			effects.append({
				"index": e,
				"type": effect.get_class() if effect != null else "",
				"enabled": AudioServer.is_bus_effect_enabled(i, e),
			})
		buses.append({
			"index": i,
			"name": String(AudioServer.get_bus_name(i)),
			"volume_db": AudioServer.get_bus_volume_db(i),
			"muted": AudioServer.is_bus_mute(i),
			"solo": AudioServer.is_bus_solo(i),
			"bypass": AudioServer.is_bus_bypassing_effects(i),
			"effects": effects,
		})
	return _ok({"buses": buses})


func _cmd_add_audio_bus(params: Dictionary) -> Dictionary:
	var bus_name := str(params.get("name", ""))
	if bus_name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	if AudioServer.get_bus_index(bus_name) != -1:
		return _fail("VALIDATION_ERROR", "An audio bus named '%s' already exists." % bus_name)
	var volume_db := float(params.get("volume_db", 0.0))
	var index := AudioServer.get_bus_count()  # add_bus(-1) appends to this index
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add audio bus %s" % bus_name)
	ur.add_do_method(AudioServer, "add_bus", -1)
	ur.add_do_method(AudioServer, "set_bus_name", index, bus_name)
	ur.add_do_method(AudioServer, "set_bus_volume_db", index, volume_db)
	ur.add_undo_method(AudioServer, "remove_bus", index)
	ur.commit_action()
	return _ok({"index": index, "name": bus_name})


func _cmd_add_audio_bus_effect(params: Dictionary) -> Dictionary:
	var bus_index := _resolve_bus_index(params.get("bus"))
	if bus_index < 0:
		return _fail("VALIDATION_ERROR", "No audio bus '%s'." % str(params.get("bus")))
	var effect_type := str(params.get("effect_type", ""))
	if not ClassDB.can_instantiate(effect_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % effect_type)
	var effect_obj: Object = ClassDB.instantiate(effect_type)
	if not (effect_obj is AudioEffect):
		if not (effect_obj is RefCounted):
			effect_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not an AudioEffect." % effect_type)
	var effect: AudioEffect = effect_obj
	_apply_props(effect, params.get("properties", {}))
	var effect_index := AudioServer.get_bus_effect_count(bus_index)  # appended position
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Add %s to bus %d" % [effect_type, bus_index])
	ur.add_do_method(AudioServer, "add_bus_effect", bus_index, effect, -1)
	ur.add_do_reference(effect)
	ur.add_undo_method(AudioServer, "remove_bus_effect", bus_index, effect_index)
	ur.commit_action()
	return _ok({
		"bus": String(AudioServer.get_bus_name(bus_index)),
		"bus_index": bus_index,
		"effect_type": effect_type,
		"effect_index": effect_index,
	})


## Resolve an audio bus reference (name string or numeric index) to a valid bus
## index, or -1 if it does not exist.
func _resolve_bus_index(bus_ref: Variant) -> int:
	if bus_ref is int or bus_ref is float:
		var i := int(bus_ref)
		return i if (i >= 0 and i < AudioServer.get_bus_count()) else -1
	return AudioServer.get_bus_index(str(bus_ref))


# --- tilemap (issue #45) ---------------------------------------------------

const _TILEMAP_FILL_LIMIT := 16384  # max cells per fill_rect (128x128) to bound undo size


func _cmd_tilemap_set_cell(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var coords_res := _parse_vec2i(params.get("coords"), "coords")
	if not coords_res["ok"]:
		return coords_res
	var atlas_res := _parse_vec2i(params.get("atlas_coords", [0, 0]), "atlas_coords")
	if not atlas_res["ok"]:
		return atlas_res
	var coords: Vector2i = coords_res["value"]
	var source_id := int(params.get("source_id", -1))
	var atlas: Vector2i = atlas_res["value"]
	var alt := int(params.get("alternative_tile", 0))
	var prev := _read_tile_cell(node, layer, coords)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set tile %v" % coords)
	ur.add_do_method(self, "_apply_tile_cell", node, layer, coords, source_id, atlas, alt)
	ur.add_undo_method(
		self, "_apply_tile_cell", node, layer, coords,
		prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
	)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"coords": [coords.x, coords.y],
		"source_id": source_id,
		"layer": layer,
	})


func _cmd_tilemap_fill_rect(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var raw_rect: Variant = params.get("rect")
	if not (raw_rect is Array) or (raw_rect as Array).size() != 4:
		return _fail("VALIDATION_ERROR", "'rect' must be [x, y, w, h].")
	var width := int(raw_rect[2])
	var height := int(raw_rect[3])
	if width <= 0 or height <= 0:
		return _fail("VALIDATION_ERROR", "rect width and height must be positive.")
	if width * height > _TILEMAP_FILL_LIMIT:
		return _fail("VALIDATION_ERROR", "Fill region %dx%d exceeds the %d-cell limit; fill smaller rects." % [width, height, _TILEMAP_FILL_LIMIT])
	var atlas_res := _parse_vec2i(params.get("atlas_coords", [0, 0]), "atlas_coords")
	if not atlas_res["ok"]:
		return atlas_res
	var origin := Vector2i(int(raw_rect[0]), int(raw_rect[1]))
	var source_id := int(params.get("source_id", -1))
	var atlas: Vector2i = atlas_res["value"]
	var alt := int(params.get("alternative_tile", 0))
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Fill tiles %dx%d" % [width, height])
	var count := 0
	for dy in height:
		for dx in width:
			var coords := origin + Vector2i(dx, dy)
			var prev := _read_tile_cell(node, layer, coords)
			ur.add_do_method(self, "_apply_tile_cell", node, layer, coords, source_id, atlas, alt)
			ur.add_undo_method(
				self, "_apply_tile_cell", node, layer, coords,
				prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
			)
			count += 1
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"rect": [origin.x, origin.y, width, height],
		"cells": count,
		"layer": layer,
	})


func _cmd_tilemap_get_cell(params: Dictionary) -> Dictionary:
	var found := _resolve_tilemap(params.get("node_path", ""), int(params.get("layer", 0)))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layer := int(params.get("layer", 0))
	var coords_res := _parse_vec2i(params.get("coords"), "coords")
	if not coords_res["ok"]:
		return coords_res
	var coords: Vector2i = coords_res["value"]
	var cell := _read_tile_cell(node, layer, coords)
	var atlas: Vector2i = cell["atlas_coords"]
	return _ok({
		"node_path": str(params.get("node_path")),
		"coords": [coords.x, coords.y],
		"source_id": cell["source_id"],
		"atlas_coords": [atlas.x, atlas.y],
		"alternative_tile": cell["alternative_tile"],
		"empty": cell["source_id"] == -1,
	})


func _cmd_tilemap_clear(params: Dictionary) -> Dictionary:
	var requested_layer: Variant = params.get("layer")
	var layer := int(requested_layer) if requested_layer != null else 0
	var found := _resolve_tilemap(params.get("node_path", ""), layer)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	# Snapshot the cells so undo can restore them, then clear. Bound the snapshot so a
	# huge layer can't build an enormous UndoRedo action and stall the editor.
	var used: Array = _used_cells(node, layer)
	if used.size() > _TILEMAP_FILL_LIMIT:
		return _fail("VALIDATION_ERROR", "Layer has %d cells, over the %d-cell undoable-clear limit; clear smaller regions with fill_rect (source_id=-1)." % [used.size(), _TILEMAP_FILL_LIMIT])
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Clear tiles")
	ur.add_do_method(self, "_clear_tile_layer", node, layer)
	for coords in used:
		var prev := _read_tile_cell(node, layer, coords)
		ur.add_undo_method(
			self, "_apply_tile_cell", node, layer, coords,
			prev["source_id"], prev["atlas_coords"], prev["alternative_tile"]
		)
	ur.commit_action()
	# TileMapLayer has no layer concept; report null. TileMap reports the cleared layer.
	var result_layer: Variant = null if node is TileMapLayer else layer
	return _ok({
		"node_path": str(params.get("node_path")),
		"layer": result_layer,
		"cleared": used.size(),
	})


func _cmd_tilemap_layers(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var layers: Array = []
	if node is TileMapLayer:
		layers.append({"index": 0, "name": String(node.name), "enabled": node.enabled})
	elif node is TileMap:
		for i in node.get_layers_count():
			layers.append({
				"index": i,
				"name": node.get_layer_name(i),
				"enabled": node.is_layer_enabled(i),
			})
	else:
		return _fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")
	return _ok({
		"node_path": str(params.get("node_path")),
		"node_type": node.get_class(),
		"layers": layers,
	})


## Resolve {ok, node} for a TileMap/TileMapLayer, validating the layer index for the
## multi-layer TileMap case (ignored for TileMapLayer).
func _resolve_tilemap(raw_path: Variant, layer: int) -> Dictionary:
	var found := _resolve(raw_path)
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if node is TileMapLayer:
		return {"ok": true, "node": node}
	if node is TileMap:
		if layer < 0 or layer >= node.get_layers_count():
			return _fail("VALIDATION_ERROR", "Layer %d is out of range (0..%d)." % [layer, node.get_layers_count() - 1])
		return {"ok": true, "node": node}
	return _fail("VALIDATION_ERROR", "Node is not a TileMap/TileMapLayer.")


## Set one cell, dispatching on node type (TileMapLayer has no layer arg). Registered
## as the UndoRedo do/undo target so both edit and revert reuse one code path.
func _apply_tile_cell(
	node: Node, layer: int, coords: Vector2i, source_id: int, atlas_coords: Vector2i, alternative_tile: int
) -> void:
	if node is TileMapLayer:
		node.set_cell(coords, source_id, atlas_coords, alternative_tile)
	else:
		node.set_cell(layer, coords, source_id, atlas_coords, alternative_tile)


## Clear all cells, dispatching on node type.
func _clear_tile_layer(node: Node, layer: int) -> void:
	if node is TileMapLayer:
		node.clear()
	else:
		node.clear_layer(layer)


## Read a cell's identifiers, dispatching on node type.
func _read_tile_cell(node: Node, layer: int, coords: Vector2i) -> Dictionary:
	if node is TileMapLayer:
		return {
			"source_id": node.get_cell_source_id(coords),
			"atlas_coords": node.get_cell_atlas_coords(coords),
			"alternative_tile": node.get_cell_alternative_tile(coords),
		}
	return {
		"source_id": node.get_cell_source_id(layer, coords),
		"atlas_coords": node.get_cell_atlas_coords(layer, coords),
		"alternative_tile": node.get_cell_alternative_tile(layer, coords),
	}


## The used (non-empty) cell coordinates, dispatching on node type.
func _used_cells(node: Node, layer: int) -> Array:
	if node is TileMapLayer:
		return node.get_used_cells()
	return node.get_used_cells(layer)


## Parse {ok, value: Vector2i} from a JSON [x, y] array or {x, y} dict, or a structured
## VALIDATION_ERROR keyed by `field`. Rejects missing/short/invalid input rather than
## silently defaulting components to 0 (which would target the wrong cell).
func _parse_vec2i(value: Variant, field: String) -> Dictionary:
	if value is Array and (value as Array).size() == 2:
		return {"ok": true, "value": Vector2i(int(value[0]), int(value[1]))}
	if value is Dictionary and value.has("x") and value.has("y"):
		return {"ok": true, "value": Vector2i(int(value["x"]), int(value["y"]))}
	return _fail("VALIDATION_ERROR", "'%s' must be [x, y] integer coordinates." % field)


# --- theme & UI (issue #46) ------------------------------------------------

func _cmd_create_theme(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is Control):
		return _fail("VALIDATION_ERROR", "Node is not a Control.")
	var theme := Theme.new()
	var save_path := str(params.get("save_path", ""))
	if not save_path.is_empty():
		if not save_path.begins_with("res://"):
			return _fail("VALIDATION_ERROR", "save_path must be a res:// path.")
		var err := ResourceSaver.save(theme, save_path)
		if err != OK:
			return _fail("INTERNAL_ERROR", "Failed to save theme to '%s' (error %d)." % [save_path, err])
		theme.take_over_path(save_path)
		EditorInterface.get_resource_filesystem().update_file(save_path)
	var prev_theme: Theme = node.theme
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create theme on %s" % node.name)
	ur.add_do_property(node, "theme", theme)
	ur.add_do_reference(theme)
	ur.add_undo_property(node, "theme", prev_theme)
	if prev_theme != null:  # keep the prior theme alive for undo
		ur.add_undo_reference(prev_theme)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "theme_path": save_path, "created": true})


func _cmd_set_theme_color(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var color: Color = Coerce.from_json(params.get("color"), TYPE_COLOR)
	var had := node.has_theme_color_override(name)
	var prev: Color = node.get_theme_color(name) if had else Color.BLACK
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Override theme color %s" % name)
	ur.add_do_method(node, "add_theme_color_override", name, color)
	ur.add_undo_method(self, "_restore_theme_color", node, name, had, prev)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "name": name})


func _cmd_set_theme_font_size(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var size := int(params.get("size", 0))
	if size <= 0:
		return _fail("VALIDATION_ERROR", "'size' must be a positive integer.")
	var had := node.has_theme_font_size_override(name)
	var prev: int = node.get_theme_font_size(name) if had else 0
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Override theme font size %s" % name)
	ur.add_do_method(node, "add_theme_font_size_override", name, size)
	ur.add_undo_method(self, "_restore_theme_font_size", node, name, had, prev)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "name": name, "size": size})


func _cmd_set_theme_stylebox(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var stylebox_type := str(params.get("stylebox_type", "StyleBoxFlat"))
	if not ClassDB.can_instantiate(stylebox_type):
		return _fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % stylebox_type)
	var sb_obj: Object = ClassDB.instantiate(stylebox_type)
	if not (sb_obj is StyleBox):
		if not (sb_obj is RefCounted):
			sb_obj.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a StyleBox." % stylebox_type)
	var stylebox: StyleBox = sb_obj
	_apply_props(stylebox, params.get("properties", {}))
	var had := node.has_theme_stylebox_override(name)
	var prev: StyleBox = node.get_theme_stylebox(name) if had else null
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Override theme stylebox %s" % name)
	ur.add_do_method(node, "add_theme_stylebox_override", name, stylebox)
	ur.add_do_reference(stylebox)
	ur.add_undo_method(self, "_restore_theme_stylebox", node, name, had, prev)
	if prev != null:  # keep the prior override StyleBox alive for undo
		ur.add_undo_reference(prev)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"name": name,
		"stylebox_type": stylebox_type,
	})


## Resolve {ok, node} for a Control, preserving _resolve's structured envelope.
func _resolve_control(raw_path: Variant) -> Dictionary:
	var found := _resolve(raw_path)
	if not found["ok"]:
		return found
	if not (found["node"] is Control):
		return _fail("VALIDATION_ERROR", "Node is not a Control.")
	return found


## Undo targets: restore a theme override to its prior state (re-apply the previous
## value if there was one, else remove the override entirely).
func _restore_theme_color(node: Control, name: String, had: bool, value: Color) -> void:
	if had:
		node.add_theme_color_override(name, value)
	else:
		node.remove_theme_color_override(name)


func _restore_theme_font_size(node: Control, name: String, had: bool, value: int) -> void:
	if had:
		node.add_theme_font_size_override(name, value)
	else:
		node.remove_theme_font_size_override(name)


func _restore_theme_stylebox(node: Control, name: String, had: bool, value: StyleBox) -> void:
	if had and value != null:
		node.add_theme_stylebox_override(name, value)
	else:
		node.remove_theme_stylebox_override(name)


# --- shaders (issue #47) ---------------------------------------------------

func _cmd_create_shader(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	if not path.begins_with("res://") or not path.ends_with(".gdshader"):
		return _fail("VALIDATION_ERROR", "shader_path must be a res:// .gdshader file.")
	var code := str(params.get("code", ""))
	if code.is_empty():
		return _fail("VALIDATION_ERROR", "'code' must be a non-empty shader source.")
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create shader %s" % path)
	ur.add_do_method(self, "_write_file_text", path, code)
	if existed:
		ur.add_undo_method(self, "_write_file_text", path, old)
	else:
		ur.add_undo_method(self, "_remove_file", path)
	ur.commit_action()
	return _ok({"shader_path": path, "created": not existed})


func _cmd_read_shader(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	if not path.ends_with(".gdshader"):
		return _fail("VALIDATION_ERROR", "shader_path must be a .gdshader file.")
	if not FileAccess.file_exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	return _ok({"shader_path": path, "code": FileAccess.get_file_as_string(path)})


func _cmd_assign_shader_material(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var prop := _material_property_for(node)
	if prop.is_empty():
		return _fail("VALIDATION_ERROR", "Node has no material slot (not a CanvasItem/GeometryInstance3D).")
	var shader_path := str(params.get("shader_path", ""))
	if not ResourceLoader.exists(shader_path):
		return _fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % shader_path)
	var shader: Resource = ResourceLoader.load(shader_path)
	if not (shader is Shader):
		return _fail("VALIDATION_ERROR", "'%s' is not a Shader." % shader_path)
	var material := ShaderMaterial.new()
	material.shader = shader
	var prev: Variant = node.get(prop)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Assign shader material to %s" % node.name)
	ur.add_do_property(node, prop, material)
	ur.add_do_reference(material)
	ur.add_undo_property(node, prop, prev)
	if prev is Resource:  # keep the prior material alive for undo
		ur.add_undo_reference(prev)
	ur.commit_action()
	return _ok({
		"node_path": str(params.get("node_path")),
		"shader_path": shader_path,
		"material_property": prop,
	})


func _cmd_set_shader_param(params: Dictionary) -> Dictionary:
	var found := _resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var prop := _material_property_for(node)
	if prop.is_empty():
		return _fail("VALIDATION_ERROR", "Node has no material slot (not a CanvasItem/GeometryInstance3D).")
	var material: Variant = node.get(prop)
	if not (material is ShaderMaterial):
		return _fail("VALIDATION_ERROR", "Node has no ShaderMaterial assigned; assign one first.", "shader_material")
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var value: Variant = _coerce_shader_value(params.get("value"), str(params.get("param_type", "")))
	var prev: Variant = material.get_shader_parameter(name)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set shader param %s" % name)
	ur.add_do_method(material, "set_shader_parameter", name, value)
	ur.add_undo_method(material, "set_shader_parameter", name, prev)
	ur.commit_action()
	return _ok({"node_path": str(params.get("node_path")), "name": name})


## The node property that holds a material, or "" if the node has no material slot.
func _material_property_for(node: Node) -> String:
	if node is CanvasItem:
		return "material"
	if node is GeometryInstance3D:
		return "material_override"
	return ""


## Coerce a JSON shader-uniform value. With an explicit param_type, convert to that
## Godot type; otherwise infer (number/bool as-is, [x,y,z(,w)] → VectorN, HTML → Color).
func _coerce_shader_value(value: Variant, param_type: String) -> Variant:
	match param_type:
		"float":
			return float(value)
		"int":
			return int(value)
		"bool":
			return bool(value)
		"color":
			return Coerce.from_json(value, TYPE_COLOR)
		"vector2":
			return Coerce.from_json(value, TYPE_VECTOR2)
		"vector3":
			return Coerce.from_json(value, TYPE_VECTOR3)
		"vector4":
			return _to_vec4(value)
		_:
			if value is Array:
				match (value as Array).size():
					2:
						return Coerce.from_json(value, TYPE_VECTOR2)
					3:
						return Coerce.from_json(value, TYPE_VECTOR3)
					4:
						return _to_vec4(value)
			if value is String and value.is_valid_html_color():
				return Color.html(value)
			return value


## Build a Vector4 from a JSON [x, y, z, w] array or {x, y, z, w} dict.
func _to_vec4(value: Variant) -> Vector4:
	if value is Array and (value as Array).size() == 4:
		return Vector4(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
	if value is Dictionary:
		return Vector4(
			float(value.get("x", 0.0)), float(value.get("y", 0.0)),
			float(value.get("z", 0.0)), float(value.get("w", 0.0))
		)
	return Vector4.ZERO


# --- editor screenshots (issue #33) ----------------------------------------

func _cmd_capture_editor_screenshot(_params: Dictionary) -> Dictionary:
	# Split the chain so any null intermediate returns a structured error, never crashes.
	var base_control := EditorInterface.get_base_control()
	if base_control == null:
		return _fail("INTERNAL_ERROR", "Editor base control is unavailable.")
	var viewport := base_control.get_viewport()
	if viewport == null:
		return _fail("INTERNAL_ERROR", "Editor viewport is unavailable.")
	var texture := viewport.get_texture()
	if texture == null:
		return _fail("INTERNAL_ERROR", "No viewport texture (no rendered frame; is a display available?).")
	var image := texture.get_image()
	if image == null:
		return _fail("INTERNAL_ERROR", "Could not capture the editor viewport image.")
	var result := _encode_png(image)
	if str(result.get("base64", "")).is_empty():
		return _fail("INTERNAL_ERROR", "PNG encoding produced no data.")
	return _ok(result)


## Encode an Image as a base64 PNG result (no temp files). Pure given an Image, so
## it is headless-testable with a synthetic image (see godot/tests/screenshot_smoke.gd).
func _encode_png(image: Image) -> Dictionary:
	return {
		"format": "png",
		"width": image.get_width(),
		"height": image.get_height(),
		"base64": Marshalls.raw_to_base64(image.save_png_to_buffer()),
	}


# --- project & filesystem (issue #32) --------------------------------------

func _cmd_get_filesystem_tree(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var max_depth := int(params.get("max_depth", -1))
	return _ok({"tree": _fs_node(directory, max_depth)})


func _cmd_search_files(params: Dictionary) -> Dictionary:
	var directory := str(params.get("directory", "res://"))
	if not directory.begins_with("res://"):
		return _fail("VALIDATION_ERROR", "directory must be inside the project (res://…).")
	if not DirAccess.dir_exists_absolute(directory):
		return _fail("RESOURCE_NOT_FOUND", "No directory '%s'." % directory)
	var name_glob := str(params.get("name_glob", ""))
	var content := str(params.get("content", ""))
	var max_results := int(params.get("max_results", 200))
	var matches: Array = []
	var truncated := _search(directory, name_glob, content, max_results, matches)
	return _ok({"matches": matches, "truncated": truncated})


func _cmd_get_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if not ProjectSettings.has_setting(setting):
		return _ok({"name": setting, "value": null, "exists": false})
	return _ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"exists": true,
	})


func _cmd_set_setting(params: Dictionary) -> Dictionary:
	var setting := str(params.get("name", ""))
	if setting.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var raw: Variant = params.get("value")
	var value: Variant = raw
	if ProjectSettings.has_setting(setting):
		# Coerce to the setting's existing type so e.g. a vector dict becomes a Vector2.
		value = Coerce.from_json(raw, typeof(ProjectSettings.get_setting(setting)))
	ProjectSettings.set_setting(setting, value)
	ProjectSettings.save()
	return _ok({
		"name": setting,
		"value": Coerce.to_json(ProjectSettings.get_setting(setting)),
		"set": true,
	})


func _cmd_path_to_uid(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	var id := ResourceLoader.get_resource_uid(path)
	if id == -1:
		return _fail("RESOURCE_NOT_FOUND", "No UID for '%s'." % path)
	return _ok({"path": path, "uid": ResourceUID.id_to_text(id)})


func _cmd_uid_to_path(params: Dictionary) -> Dictionary:
	var uid := str(params.get("uid", ""))
	var id := ResourceUID.text_to_id(uid)
	if id == -1 or not ResourceUID.has_id(id):
		return _fail("RESOURCE_NOT_FOUND", "Unknown UID '%s'." % uid)
	return _ok({"uid": uid, "path": ResourceUID.get_id_path(id)})


## Recursive filesystem node { name, path, type, children }. Skips hidden entries.
func _fs_node(dir_path: String, max_depth: int) -> Dictionary:
	var node: Dictionary = {
		"name": ("res://" if dir_path == "res://" else dir_path.trim_suffix("/").get_file()),
		"path": dir_path,
		"type": "directory",
		"children": [],
	}
	if max_depth == 0:
		return node
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return node
	var child_depth: int = (max_depth - 1) if max_depth > 0 else -1
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				node["children"].append(_fs_node(full, child_depth))
			else:
				node["children"].append({"name": name, "path": full, "type": "file"})
		name = dir.get_next()
	dir.list_dir_end()
	return node


## Recursively collect files matching name_glob and/or content; returns true if the
## result was truncated at max_results.
func _search(dir_path: String, name_glob: String, content: String, max_results: int, out: Array) -> bool:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return false
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not name.begins_with("."):
			var full := dir_path.path_join(name)
			if dir.current_is_dir():
				if _search(full, name_glob, content, max_results, out):
					dir.list_dir_end()
					return true
			elif (name_glob.is_empty() or name.match(name_glob)) \
					and (content.is_empty() or _file_contains(full, content)):
				out.append(full)
				if out.size() >= max_results:
					dir.list_dir_end()
					return true
		name = dir.get_next()
	dir.list_dir_end()
	return false


func _file_contains(path: String, needle: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	if file.get_length() > 2_000_000:  # skip large/binary files
		file.close()
		return false
	var text := file.get_as_text()
	file.close()
	return text.contains(needle)


# --- resource files + autoloads (issue #34) --------------------------------

func _cmd_read_resource(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	return _ok({
		"resource_path": path,
		"type": res.get_class(),
		"script": Inspect.script_path(res),
		"properties": Inspect.resource_properties(res),
	})


func _cmd_create_resource(params: Dictionary) -> Dictionary:
	var res_type := str(params.get("type", ""))
	var path := str(params.get("resource_path", ""))
	if not ClassDB.class_exists(res_type) or not ClassDB.can_instantiate(res_type):
		return _fail("VALIDATION_ERROR", "Unknown or non-instantiable type '%s'." % res_type)
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must end with .tres or .res.")
	var instance: Object = ClassDB.instantiate(res_type)
	if not (instance is Resource):
		# Free any discarded non-RefCounted instance (Node or bare Object) to avoid
		# leaking; RefCounted instances free themselves when the ref drops.
		if not (instance is RefCounted):
			instance.free()
		return _fail("VALIDATION_ERROR", "'%s' is not a Resource type." % res_type)

	var res: Resource = instance
	var properties: Dictionary = params.get("properties", {})
	for key in properties:
		var prop_type := _property_type(res, str(key))
		if prop_type != -1:
			res.set(str(key), Coerce.from_json(properties[key], prop_type))

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var err := ResourceSaver.save(res, path)
	if err != OK:
		return _fail("INTERNAL_ERROR", "Failed to save resource to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)
	return _ok({"resource_path": path, "type": res_type, "created": true})


func _cmd_set_resource_property(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	var property := str(params.get("property", ""))
	var prop_type := _property_type(res, property)
	if prop_type == -1:
		return _fail("VALIDATION_ERROR", "Resource has no property '%s'." % property)

	var old_value: Variant = res.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [path.get_file(), property])
	ur.add_do_method(self, "_set_and_save_resource", path, property, new_value)
	ur.add_undo_method(self, "_set_and_save_resource", path, property, old_value)
	ur.commit_action()
	return _ok({
		"resource_path": path,
		"property": property,
		"value": Coerce.to_json(ResourceLoader.load(path).get(property)),
	})


func _cmd_register_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var path := str(params.get("path", ""))
	if autoload_name.is_empty():
		return _fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	if not ResourceLoader.exists(path):
		return _fail("RESOURCE_NOT_FOUND", "No script/scene at '%s'." % path)
	# "*" prefix enables the autoload as a global singleton.
	ProjectSettings.set_setting("autoload/" + autoload_name, "*" + path)
	ProjectSettings.save()
	return _ok({"name": autoload_name, "path": path, "registered": true})


func _cmd_unregister_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var key := "autoload/" + autoload_name
	if not ProjectSettings.has_setting(key):
		return _ok({"name": autoload_name, "unregistered": false})
	ProjectSettings.set_setting(key, null)
	ProjectSettings.save()
	return _ok({"name": autoload_name, "unregistered": true})


## Load a resource, set a property, and re-save — the UndoRedo callback for edits.
func _set_and_save_resource(path: String, property: String, value: Variant) -> void:
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return
	res.set(property, value)
	ResourceSaver.save(res, path)
	EditorInterface.get_resource_filesystem().update_file(path)


## Set owner of a node and its whole subtree to the scene root so it is saved.
func _own_recursive(node: Node, root: Node) -> void:
	if node != root:
		node.owner = root
	for child in node.get_children():
		_own_recursive(child, root)


# --- editor-state helpers --------------------------------------------------

## Resolve a node by scene-relative path, returning {ok, node} or an error body.
func _resolve(raw_path: Variant) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node: Node = root.get_node_or_null(NodePath(str(raw_path)))
	if node == null:
		return _fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(raw_path))
	return {"ok": true, "node": node}


## The Variant.Type of an object's property, or -1 if it has no such property.
func _property_type(obj: Object, property: String) -> int:
	for entry in obj.get_property_list():
		if entry["name"] == property:
			return int(entry["type"])
	return -1


func _scene_name(root: Node) -> String:
	if not root.scene_file_path.is_empty():
		return root.scene_file_path.get_file()
	return String(root.name)


func _autoloads() -> Dictionary:
	var autoloads: Dictionary = {}
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("autoload/"):
			autoloads[key.trim_prefix("autoload/")] = str(ProjectSettings.get_setting(key, ""))
	return autoloads


func _input_actions() -> Array:
	var actions: Array = []
	for entry in ProjectSettings.get_property_list():
		var key: String = entry["name"]
		if key.begins_with("input/"):
			actions.append(key.trim_prefix("input/"))
	return actions


# --- response builders -----------------------------------------------------

func _ok(result: Dictionary) -> Dictionary:
	return {"ok": true, "result": result}


func _fail(code: String, hint: String, required: String = "") -> Dictionary:
	var body: Dictionary = {"ok": false, "error": code, "hint": hint}
	if not required.is_empty():
		body["required"] = required
	return body
