@tool
class_name MCPThemeUIHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
const ThemeRead := preload("res://addons/godot_mcp/theme_read.gd")
## Domain handler: theme ui.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_create_theme"] = _cmd_create_theme
	handlers["cmd_set_theme_color"] = _cmd_set_theme_color
	handlers["cmd_set_theme_font_size"] = _cmd_set_theme_font_size
	handlers["cmd_set_theme_stylebox"] = _cmd_set_theme_stylebox
	handlers["cmd_get_node_theme_overrides"] = _cmd_get_node_theme_overrides


# -- handlers ----------------------------------------------------------------

func _cmd_create_theme(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	if not (node is Control):
		return _router._fail("VALIDATION_ERROR", "Node is not a Control.")
	var theme := Theme.new()
	var save_path := str(params.get("save_path", ""))
	if not save_path.is_empty():
		if not save_path.begins_with("res://"):
			return _router._fail("VALIDATION_ERROR", "save_path must be a res:// path.")
		var err := ResourceSaver.save(theme, save_path)
		if err != OK:
			return _router._fail("INTERNAL_ERROR", "Failed to save theme to '%s' (error %d)." % [save_path, err])
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
	return _router._ok({"node_path": str(params.get("node_path")), "theme_path": save_path, "created": true})



func _cmd_set_theme_color(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var color: Color = Coerce.from_json(params.get("color"), TYPE_COLOR)
	var had := node.has_theme_color_override(name)
	var prev: Color = node.get_theme_color(name) if had else Color.BLACK
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Override theme color %s" % name)
	ur.add_do_method(node, "add_theme_color_override", name, color)
	ur.add_undo_method(self, "_restore_theme_color", node, name, had, prev)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "name": name})



func _cmd_set_theme_font_size(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var size := int(params.get("size", 0))
	if size <= 0:
		return _router._fail("VALIDATION_ERROR", "'size' must be a positive integer.")
	var had := node.has_theme_font_size_override(name)
	var prev: int = node.get_theme_font_size(name) if had else 0
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Override theme font size %s" % name)
	ur.add_do_method(node, "add_theme_font_size_override", name, size)
	ur.add_undo_method(self, "_restore_theme_font_size", node, name, had, prev)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "name": name, "size": size})



func _cmd_set_theme_stylebox(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var stylebox_type := str(params.get("stylebox_type", "StyleBoxFlat"))
	if not ClassDB.can_instantiate(stylebox_type):
		return _router._fail("VALIDATION_ERROR", "Cannot instantiate '%s'." % stylebox_type)
	var sb_obj: Object = ClassDB.instantiate(stylebox_type)
	if not (sb_obj is StyleBox):
		if not (sb_obj is RefCounted):
			sb_obj.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a StyleBox." % stylebox_type)
	var stylebox: StyleBox = sb_obj
	_router._apply_props(stylebox, params.get("properties", {}))
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
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"name": name,
		"stylebox_type": stylebox_type,
	})


## Read a Control's per-node theme overrides — colors / font_sizes / styleboxes (issue
## #219 G7). The inverse of set_theme_color / set_theme_font_size / set_theme_stylebox;
## delegates the pure serialization to MCPThemeRead.
func _cmd_get_node_theme_overrides(params: Dictionary) -> Dictionary:
	var found := _resolve_control(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Control = found["node"]
	var data: Dictionary = ThemeRead.overrides(node)
	data["node_path"] = str(params.get("node_path"))
	return _router._ok(data)


func _resolve_control(raw_path: Variant) -> Dictionary:
	var found := _router._resolve(raw_path)
	if not found["ok"]:
		return found
	if not (found["node"] is Control):
		return _router._fail("VALIDATION_ERROR", "Node is not a Control.")
	return found


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


