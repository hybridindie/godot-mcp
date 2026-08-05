@tool
class_name MCPShadersHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: shaders.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter



func _to_vec4(value: Variant) -> Vector4:
	if value is Array and (value as Array).size() == 4:
		return Vector4(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
	if value is Dictionary:
		return Vector4(
			float(value.get("x", 0.0)), float(value.get("y", 0.0)),
			float(value.get("z", 0.0)), float(value.get("w", 0.0))
		)
	return Vector4.ZERO


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_assign_shader_material"] = _cmd_assign_shader_material
	handlers["cmd_create_shader"] = _cmd_create_shader
	handlers["cmd_get_shader_param"] = _cmd_get_shader_param
	handlers["cmd_read_shader"] = _cmd_read_shader
	handlers["cmd_set_shader_param"] = _cmd_set_shader_param


# -- handlers ----------------------------------------------------------------

func _cmd_create_shader(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	if not path.begins_with("res://") or not path.ends_with(".gdshader"):
		return _router._fail("VALIDATION_ERROR", "shader_path must be a res:// .gdshader file.")
	var code := str(params.get("code", ""))
	if code.is_empty():
		return _router._fail("VALIDATION_ERROR", "'code' must be a non-empty shader source.")
	var existed := FileAccess.file_exists(path)
	var old := FileAccess.get_file_as_string(path) if existed else ""
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Create shader %s" % path)
	ur.add_do_method(_router, "_write_file_text", path, code)
	if existed:
		ur.add_undo_method(_router, "_write_file_text", path, old)
	else:
		# Undo a freshly-created shader: remove the file and its Godot 4.4+ .uid sidecar
		# so nothing is left orphaned.
		ur.add_undo_method(_router, "_remove_file_with_uid", path)
	ur.commit_action()
	return _router._ok({"shader_path": path, "created": not existed})



func _cmd_read_shader(params: Dictionary) -> Dictionary:
	var path := str(params.get("shader_path", ""))
	if not path.ends_with(".gdshader"):
		return _router._fail("VALIDATION_ERROR", "shader_path must be a .gdshader file.")
	if not FileAccess.file_exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % path)
	return _router._ok({"shader_path": path, "code": FileAccess.get_file_as_string(path)})



func _cmd_assign_shader_material(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var prop := _material_property_for(node)
	if prop.is_empty():
		return _router._fail("VALIDATION_ERROR", "Node has no material slot (not a CanvasItem/GeometryInstance3D).")
	var shader_path := str(params.get("shader_path", ""))
	if not ResourceLoader.exists(shader_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No shader at '%s'." % shader_path)
	var shader: Resource = ResourceLoader.load(shader_path)
	if not (shader is Shader):
		return _router._fail("VALIDATION_ERROR", "'%s' is not a Shader." % shader_path)
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
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"shader_path": shader_path,
		"material_property": prop,
	})



func _cmd_set_shader_param(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var prop := _material_property_for(node)
	if prop.is_empty():
		return _router._fail("VALIDATION_ERROR", "Node has no material slot (not a CanvasItem/GeometryInstance3D).")
	var material: Variant = node.get(prop)
	if not (material is ShaderMaterial):
		return _router._fail("VALIDATION_ERROR", "Node has no ShaderMaterial assigned; assign one first.", "shader_material")
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var value: Variant = _coerce_shader_value(params.get("value"), str(params.get("param_type", "")))
	var prev: Variant = material.get_shader_parameter(name)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set shader param %s" % name)
	ur.add_do_method(material, "set_shader_parameter", name, value)
	ur.add_undo_method(material, "set_shader_parameter", name, prev)
	ur.commit_action()
	return _router._ok({"node_path": str(params.get("node_path")), "name": name})


func _cmd_get_shader_param(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("node_path", ""))
	if not found["ok"]:
		return found
	var node: Node = found["node"]
	var prop := _material_property_for(node)
	if prop.is_empty():
		return _router._fail("VALIDATION_ERROR", "Node has no material slot (not a CanvasItem/GeometryInstance3D).")
	var material: Variant = node.get(prop)
	if not (material is ShaderMaterial):
		return _router._fail("VALIDATION_ERROR", "Node has no ShaderMaterial assigned; assign one first.", "shader_material")
	var name := str(params.get("name", ""))
	if name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	var exists := false
	for param in material.get_shader_parameter_list():
		if param.name == name:
			exists = true
			break
	var value: Variant = material.get_shader_parameter(name)
	return _router._ok({
		"node_path": str(params.get("node_path")),
		"name": name,
		"value": Coerce.to_json(value),
		"exists": exists,
	})


func _material_property_for(node: Node) -> String:
	if node is CanvasItem:
		return "material"
	if node is GeometryInstance3D:
		return "material_override"
	return ""


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
			return _router._to_vec4(value)
		_:
			if value is Array:
				match (value as Array).size():
					2:
						return Coerce.from_json(value, TYPE_VECTOR2)
					3:
						return Coerce.from_json(value, TYPE_VECTOR3)
					4:
						return _router._to_vec4(value)
			if value is String and value.is_valid_html_color():
				return Color.html(value)
			return value


