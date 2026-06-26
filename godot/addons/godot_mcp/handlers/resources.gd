@tool
class_name MCPResourcesHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: resources.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_create_resource"] = _cmd_create_resource
	handlers["cmd_read_resource"] = _cmd_read_resource
	handlers["cmd_register_autoload"] = _cmd_register_autoload
	handlers["cmd_set_resource_property"] = _cmd_set_resource_property
	handlers["cmd_unregister_autoload"] = _cmd_unregister_autoload


# -- handlers ----------------------------------------------------------------

func _cmd_read_resource(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _router._fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	return _router._ok({
		"resource_path": path,
		"type": res.get_class(),
		"script": Inspect.script_path(res),
		"properties": Inspect.resource_properties(res),
	})



func _cmd_create_resource(params: Dictionary) -> Dictionary:
	var res_type := str(params.get("type", ""))
	var path := str(params.get("resource_path", ""))
	if not ClassDB.class_exists(res_type) or not ClassDB.can_instantiate(res_type):
		return _router._fail("VALIDATION_ERROR", "Unknown or non-instantiable type '%s'." % res_type)
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _router._fail("VALIDATION_ERROR", "resource_path must end with .tres or .res.")
	var instance: Object = ClassDB.instantiate(res_type)
	if not (instance is Resource):
		# Free any discarded non-RefCounted instance (Node or bare Object) to avoid
		# leaking; RefCounted instances free themselves when the ref drops.
		if not (instance is RefCounted):
			instance.free()
		return _router._fail("VALIDATION_ERROR", "'%s' is not a Resource type." % res_type)

	var res: Resource = instance
	var properties: Dictionary = params.get("properties", {})
	for key in properties:
		var prop_type := _router._property_type(res, str(key))
		if prop_type != -1:
			res.set(str(key), Coerce.from_json(properties[key], prop_type))

	var base_dir := path.get_base_dir()
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)
	var err := ResourceSaver.save(res, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save resource to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)
	return _router._ok({"resource_path": path, "type": res_type, "created": true})



func _cmd_set_resource_property(params: Dictionary) -> Dictionary:
	var path := str(params.get("resource_path", ""))
	if not (path.ends_with(".tres") or path.ends_with(".res")):
		return _router._fail("VALIDATION_ERROR", "resource_path must be a .tres/.res file.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var res: Resource = ResourceLoader.load(path)
	if res == null:
		return _router._fail("INTERNAL_ERROR", "Failed to load resource '%s'." % path)
	var property := str(params.get("property", ""))
	var prop_type := _router._property_type(res, property)
	if prop_type == -1:
		return _router._fail("VALIDATION_ERROR", "Resource has no property '%s'." % property)

	var old_value: Variant = res.get(property)
	var new_value: Variant = Coerce.from_json(params.get("value"), prop_type)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Set %s.%s" % [path.get_file(), property])
	# _set_and_save_resource lives on the router, not this handler — target _router
	# so the UndoRedo actually invokes it (else the set silently never runs).
	ur.add_do_method(_router, "_set_and_save_resource", path, property, new_value)
	ur.add_undo_method(_router, "_set_and_save_resource", path, property, old_value)
	ur.commit_action()
	return _router._ok({
		"resource_path": path,
		"property": property,
		"value": Coerce.to_json(ResourceLoader.load(path).get(property)),
	})



func _cmd_register_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var path := str(params.get("path", ""))
	if autoload_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'name' must be a non-empty string.")
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No script/scene at '%s'." % path)
	# "*" prefix enables the autoload as a global singleton.
	ProjectSettings.set_setting("autoload/" + autoload_name, "*" + path)
	ProjectSettings.save()
	return _router._ok({"name": autoload_name, "path": path, "registered": true})



func _cmd_unregister_autoload(params: Dictionary) -> Dictionary:
	var autoload_name := str(params.get("name", ""))
	var key := "autoload/" + autoload_name
	if not ProjectSettings.has_setting(key):
		return _router._ok({"name": autoload_name, "unregistered": false})
	ProjectSettings.set_setting(key, null)
	ProjectSettings.save()
	return _router._ok({"name": autoload_name, "unregistered": true})


