@tool
class_name MCPBatchHandlers
extends RefCounted
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
## Domain handler: batch.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")

var _router: MCPCommandRouter






func _parse_dependency(dep: String) -> Dictionary:
	var parts := dep.split("::", false)
	var dpath := ""
	for part in parts:
		if part.begins_with("res://") or part.begins_with("uid://"):
			dpath = part
	var dtype := ""
	if parts.size() > 1:
		var last: String = parts[parts.size() - 1]
		if not (last.begins_with("res://") or last.begins_with("uid://")):
			dtype = last
	return {"raw": dep, "path": dpath, "type": dtype}


func _cross_scene_one(
	path: String, type_name: String, property: String, value: Variant, dry_run: bool, current: String
) -> Dictionary:
	if not path.begins_with("res://") or not (path.ends_with(".tscn") or path.ends_with(".scn")):
		return {"scene": path, "modified": 0, "error": "not a res:// scene file"}
	if path == current:
		return {"scene": path, "modified": 0, "error": "scene is currently being edited; use batch_set_property"}
	if not ResourceLoader.exists(path):
		return {"scene": path, "modified": 0, "error": "not found"}
	var packed: Variant = ResourceLoader.load(path, "PackedScene")
	if not (packed is PackedScene):
		return {"scene": path, "modified": 0, "error": "not a PackedScene"}
	var root: Node = packed.instantiate(PackedScene.GEN_EDIT_STATE_MAIN)
	if root == null:
		return {"scene": path, "modified": 0, "error": "could not instantiate"}
	var targets: Array = root.find_children("*", type_name, true, false)
	if root.is_class(type_name):
		targets.push_front(root)
	var modified := 0
	for node in targets:
		var prop_type := _router._property_type(node, property)
		if prop_type == -1:
			continue
		if not dry_run:
			node.set(property, Coerce.from_json(value, prop_type))
		modified += 1
	var error := ""
	if not dry_run and modified > 0:
		var repacked := PackedScene.new()
		if repacked.pack(root) != OK:
			error = "pack failed"
		elif ResourceSaver.save(repacked, path) != OK:
			error = "save failed"
		else:
			EditorInterface.get_resource_filesystem().update_file(path)
	root.free()
	return {"scene": path, "modified": modified, "error": error}


## Parse a ResourceLoader.get_dependencies entry ("uid::path::type" / "path::type" / "path")
## into {raw, path, type}.
func _batch_targets(root: Node, params: Dictionary) -> Variant:
	var node_paths: Variant = params.get("node_paths")
	var type_name := str(params.get("type", ""))
	if node_paths is Array and not (node_paths as Array).is_empty():
		var nodes: Array = []
		for raw in node_paths:
			var raw_str := str(raw)
			if raw_str.begins_with("/"):
				raw_str = raw_str.substr(1)
			if raw_str.is_empty():
				raw_str = "."
			var node := root.get_node_or_null(NodePath(raw_str))
			if node == null:
				return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % str(raw))
			nodes.append(node)
		return nodes
	if not type_name.is_empty():
		var matches: Array = root.find_children("*", type_name, true, false)
		if root.is_class(type_name):
			matches.push_front(root)
		return matches
	return _router._fail("VALIDATION_ERROR", "Provide 'node_paths' or 'type' to select targets.")


## Edit one scene file on disk. Skips the currently-edited scene (its in-memory copy is
## authoritative and would clobber the change); background/closed scenes are edited and
## re-scanned. Loads with GEN_EDIT_STATE_MAIN so the re-pack round-trips faithfully.
func _node_summary(node: Node, root: Node) -> Dictionary:
	return {
		"path": Inspect.relative_path(node, root) if root != null else String(node.name),
		"name": String(node.name),
		"type": node.get_class(),
	}


## Resolve batch targets to an Array of Nodes, or a structured error Dictionary.
## Explicit node_paths win; otherwise all nodes of `type` under the scene root.
func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_batch_set_property"] = _cmd_batch_set_property
	handlers["cmd_cross_scene_set_property"] = _cmd_cross_scene_set_property
	handlers["cmd_find_nodes_by_type"] = _cmd_find_nodes_by_type
	handlers["cmd_get_dependencies"] = _cmd_get_dependencies


# -- handlers ----------------------------------------------------------------

func _cmd_find_nodes_by_type(params: Dictionary) -> Dictionary:
	var found := _router._resolve(params.get("parent_path", "."))
	if not found["ok"]:
		return found
	var parent: Node = found["node"]
	var type_name := str(params.get("type", ""))
	if type_name.is_empty():
		return _router._fail("VALIDATION_ERROR", "'type' must be a non-empty class name.")
	var recursive := bool(params.get("recursive", true))
	var root := EditorInterface.get_edited_scene_root()
	var nodes: Array = []
	if parent.is_class(type_name):
		nodes.append(_node_summary(parent, root))
	for node in parent.find_children("*", type_name, recursive, false):
		nodes.append(_node_summary(node, root))
	return _router._ok({"type": type_name, "nodes": nodes, "count": nodes.size()})



func _cmd_batch_set_property(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var property := str(params.get("property", ""))
	if property.is_empty():
		return _router._fail("VALIDATION_ERROR", "'property' must be a non-empty string.")
	var targets := _batch_targets(root, params)
	if targets is Dictionary:
		return targets  # structured error from target resolution
	var value: Variant = params.get("value")
	var dry_run := bool(params.get("dry_run", false))
	var applied: Array = []
	var skipped: Array = []
	var to_apply: Array = []  # only nodes that actually have the property
	for node in targets:
		var prop_type := _router._property_type(node, property)
		if prop_type == -1:
			skipped.append({"path": Inspect.relative_path(node, root), "reason": "no such property"})
			continue
		applied.append(Inspect.relative_path(node, root))
		to_apply.append({"node": node, "value": Coerce.from_json(value, prop_type)})
	# Only open an UndoRedo action when at least one set is scheduled (no no-op steps).
	if not dry_run and not to_apply.is_empty():
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Batch set %s on %d nodes" % [property, to_apply.size()])
		for item in to_apply:
			ur.add_do_property(item["node"], property, item["value"])
			ur.add_undo_property(item["node"], property, item["node"].get(property))
		ur.commit_action()
	return _router._ok({
		"property": property,
		"applied": applied,
		"skipped": skipped,
		"count": applied.size(),
		"dry_run": dry_run,
	})



func _cmd_cross_scene_set_property(params: Dictionary) -> Dictionary:
	var scenes: Variant = params.get("scenes")
	if not (scenes is Array) or (scenes as Array).is_empty():
		return _router._fail("VALIDATION_ERROR", "'scenes' must be a non-empty array of res:// scene paths.")
	var type_name := str(params.get("type", ""))
	var property := str(params.get("property", ""))
	if type_name.is_empty() or property.is_empty():
		return _router._fail("VALIDATION_ERROR", "'type' and 'property' are required.")
	var value: Variant = params.get("value")
	var dry_run := bool(params.get("dry_run", false))
	var current := EditorInterface.get_edited_scene_root()
	var current_path := current.scene_file_path if current != null else ""
	var results: Array = []
	var total := 0
	for raw in scenes:
		var res := _cross_scene_one(str(raw), type_name, property, value, dry_run, current_path)
		results.append(res)
		total += int(res.get("modified", 0))
	return _router._ok({"results": results, "total_modified": total, "scenes": results.size(), "dry_run": dry_run})



func _cmd_get_dependencies(params: Dictionary) -> Dictionary:
	var path := str(params.get("path", ""))
	# ResourceLoader.exists handles uid:// and imported/remapped resources that
	# FileAccess.file_exists would miss.
	if not ResourceLoader.exists(path):
		return _router._fail("RESOURCE_NOT_FOUND", "No resource at '%s'." % path)
	var deps := ResourceLoader.get_dependencies(path)
	var out: Array = []
	for dep in deps:
		out.append(_parse_dependency(dep))
	return _router._ok({"path": path, "dependencies": out, "count": out.size()})



