@tool
class_name MCPMeshLibraryHandlers
extends RefCounted
## Domain handler: mesh library.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_add_mesh_library_item"] = _cmd_add_mesh_library_item
	handlers["cmd_create_mesh_library"] = _cmd_create_mesh_library


# -- handlers ----------------------------------------------------------------

func _cmd_create_mesh_library(params: Dictionary) -> Dictionary:
	var node_path := str(params.get("node_path", ""))
	var save_path := str(params.get("save_path", ""))
	if node_path.is_empty() and save_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "Provide 'node_path' to assign the MeshLibrary and/or 'save_path' to save it as a .tres.")
	var library := MeshLibrary.new()
	if not save_path.is_empty():
		if not save_path.begins_with("res://"):
			return _router._fail("VALIDATION_ERROR", "save_path must be a res:// path.")
		var saved := _save_mesh_library_file(library, save_path)
		if not saved["ok"]:
			return saved
		library.take_over_path(save_path)
	if not node_path.is_empty():
		var found := _router._resolve(node_path)
		if not found["ok"]:
			return found
		var node: Node = found["node"]
		if not (node is GridMap):
			return _router._fail("VALIDATION_ERROR", "Node is not a GridMap.")
		var prev: MeshLibrary = node.mesh_library
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Create MeshLibrary on %s" % node.name)
		ur.add_do_property(node, "mesh_library", library)
		ur.add_do_reference(library)
		ur.add_undo_property(node, "mesh_library", prev)
		if prev != null:  # keep the prior MeshLibrary alive for undo
			ur.add_undo_reference(prev)
		ur.commit_action()
	return _router._ok({
		"node_path": node_path,
		"library_path": save_path,
		"created": true,
	})



func _cmd_add_mesh_library_item(params: Dictionary) -> Dictionary:
	var resolved := _resolve_mesh_library(params)
	if not resolved["ok"]:
		return resolved
	var library: MeshLibrary = resolved["library"]
	var mesh_res := _resolve_mesh(params)
	if not mesh_res["ok"]:
		return mesh_res
	var mesh: Mesh = mesh_res["mesh"]
	var requested: Variant = params.get("item_id")
	var item_id := int(requested) if requested != null else library.get_last_unused_item_id()
	if item_id < 0:
		return _router._fail("VALIDATION_ERROR", "'item_id' must be non-negative.")
	if library.get_item_list().has(item_id):
		return _router._fail("VALIDATION_ERROR", "Item id %d already exists in the MeshLibrary." % item_id)
	var item_name := str(params.get("name", ""))
	if resolved["backing"] == "node":
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Add MeshLibrary item %d" % item_id)
		ur.add_do_method(library, "create_item", item_id)
		ur.add_do_method(library, "set_item_mesh", item_id, mesh)
		if not item_name.is_empty():
			ur.add_do_method(library, "set_item_name", item_id, item_name)
		ur.add_do_reference(mesh)
		ur.add_undo_method(library, "remove_item", item_id)
		ur.commit_action()
	else:
		library.create_item(item_id)
		library.set_item_mesh(item_id, mesh)
		if not item_name.is_empty():
			library.set_item_name(item_id, item_name)
		var saved := _save_mesh_library_file(library, resolved["path"])
		if not saved["ok"]:
			return saved
	return _router._ok({
		"node_path": str(params.get("node_path", "")),
		"library_path": str(params.get("library_path", "")),
		"item_id": item_id,
		"name": item_name,
		"mesh_type": str(params.get("mesh_type", "")),
		"mesh_path": str(params.get("mesh_path", "")),
	})


func _resolve_mesh_library(params: Dictionary) -> Dictionary:
	var node_path := str(params.get("node_path", ""))
	var library_path := str(params.get("library_path", ""))
	if not node_path.is_empty() and not library_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "Pass only one of 'node_path' or 'library_path', not both.")
	if not node_path.is_empty():
		var found := _router._resolve(node_path)
		if not found["ok"]:
			return found
		var node: Node = found["node"]
		if not (node is GridMap):
			return _router._fail("VALIDATION_ERROR", "Node is not a GridMap.")
		var lib: MeshLibrary = node.mesh_library
		if lib == null:
			return _router._fail("VALIDATION_ERROR", "GridMap has no mesh_library; create one first with create_mesh_library.", "mesh_library")
		return {"ok": true, "library": lib, "backing": "node", "node": node}
	if not library_path.is_empty():
		if not ResourceLoader.exists(library_path):
			return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % library_path)
		var res: Resource = ResourceLoader.load(library_path)
		if not (res is MeshLibrary):
			return _router._fail("VALIDATION_ERROR", "'%s' is not a MeshLibrary." % library_path)
		return {"ok": true, "library": res, "backing": "file", "path": library_path}
	return _router._fail("VALIDATION_ERROR", "Provide a 'node_path' (GridMap) or a 'library_path' (.tres).")


func _resolve_mesh(params: Dictionary) -> Dictionary:
	var mesh_type := str(params.get("mesh_type", ""))
	var mesh_path := str(params.get("mesh_path", ""))
	if not mesh_type.is_empty() and not mesh_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "Pass only one of 'mesh_type' or 'mesh_path', not both.")
	if not mesh_path.is_empty():
		if not ResourceLoader.exists(mesh_path):
			return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'. Import the mesh into the project first." % mesh_path)
		var res: Resource = ResourceLoader.load(mesh_path)
		if not (res is Mesh):
			return _router._fail("VALIDATION_ERROR", "'%s' is not a Mesh resource (.glb/.gltf import as scenes, not meshes)." % mesh_path)
		return {"ok": true, "mesh": res}
	if not mesh_type.is_empty():
		if not ClassDB.can_instantiate(mesh_type):
			return _router._fail("VALIDATION_ERROR", "Cannot instantiate mesh '%s'." % mesh_type)
		var obj: Object = ClassDB.instantiate(mesh_type)
		if not (obj is Mesh):
			if not (obj is RefCounted):
				obj.free()
			return _router._fail("VALIDATION_ERROR", "'%s' is not a Mesh." % mesh_type)
		_router._apply_props(obj, params.get("properties", {}))
		return {"ok": true, "mesh": obj}
	return _router._fail("VALIDATION_ERROR", "Provide 'mesh_type' (a primitive like BoxMesh) or 'mesh_path' (a Mesh resource).")


func _save_mesh_library_file(library: MeshLibrary, path: String) -> Dictionary:
	var err := ResourceSaver.save(library, path)
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save MeshLibrary to '%s' (error %d)." % [path, err])
	EditorInterface.get_resource_filesystem().update_file(path)
	return {"ok": true}


