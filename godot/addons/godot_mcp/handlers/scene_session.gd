@tool
class_name MCPSceneSessionHandlers
extends RefCounted
## Domain handler: scene session.
##
## Registered by the router on _init().  Each handler receives params dict and
## returns a response body (without id) via the router's _ok / _fail builders.

const Inspect := preload("../scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_close_scene"] = _cmd_close_scene
	handlers["cmd_extract_scene"] = _cmd_extract_scene
	handlers["cmd_instance_scene"] = _cmd_instance_scene
	handlers["cmd_list_open_scenes"] = _cmd_list_open_scenes
	handlers["cmd_open_scene"] = _cmd_open_scene
	handlers["cmd_reload_scene"] = _cmd_reload_scene
	handlers["cmd_rescan_filesystem"] = _cmd_rescan_filesystem
	handlers["cmd_save_all_scenes"] = _cmd_save_all_scenes
	handlers["cmd_select_nodes"] = _cmd_select_nodes


# -- handlers ----------------------------------------------------------------

func _cmd_close_scene(params: Dictionary) -> Dictionary:
	# Closes a scene tab, discarding unsaved changes (confirm is enforced
	# server-side; honored defensively here). EditorInterface.close_scene() (4.4+)
	# closes the currently active scene; to close a specific open scene by path
	# we activate it first via open_scene_from_path, then close.
	if not params.get("confirm", false):
		return _router._fail("PRECONDITION_FAILED", "close_scene discards unsaved changes. Set confirm=True to proceed (or call save_scene first).", "confirm")
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var scene_path := str(params.get("scene_path", ""))
	# Resolve the path of the scene we will actually close.
	var target_path := scene_path
	if target_path.is_empty():
		target_path = root.scene_file_path
		if target_path.is_empty():
			return _router._fail("PRECONDITION_FAILED", "The active scene has no path on disk yet.", "scene_path")
	# If a specific path was requested and it isn't the active scene, activate it.
	if not scene_path.is_empty() and scene_path != root.scene_file_path:
		var open_paths: PackedStringArray = EditorInterface.get_open_scenes()
		var is_open := false
		for p in open_paths:
			if str(p) == scene_path:
				is_open = true
				break
		if not is_open:
			return _router._fail("PRECONDITION_FAILED", "Scene '%s' is not open. Open it first." % scene_path, "open_scene")
		# open_scene_from_path returns void (Godot 4.6 docs); re-read the active
		# scene root to confirm activation took effect before closing, so we
		# never close the wrong (previously active) scene if activation failed.
		EditorInterface.open_scene_from_path(scene_path)
		var activated := EditorInterface.get_edited_scene_root()
		if activated == null or activated.scene_file_path != scene_path:
			return _router._fail("INTERNAL_ERROR", "Failed to activate scene '%s' for closing." % scene_path)
	var err := EditorInterface.close_scene()
	if err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to close scene '%s' (error %d)." % [target_path, err])
	return _router._ok({"scene_path": target_path, "closed": true})

func _cmd_open_scene(params: Dictionary) -> Dictionary:
	var scene_path := str(params.get("scene_path", ""))
	if scene_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "scene_path is required.")
	if not FileAccess.file_exists(scene_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No scene at '%s'." % scene_path)
	var open_paths: PackedStringArray = EditorInterface.get_open_scenes()
	var already_open := false
	for p in open_paths:
		if str(p) == scene_path:
			already_open = true
			break
	EditorInterface.open_scene_from_path(scene_path)
	return _router._ok({"scene_path": scene_path, "opened": true, "already_open": already_open})



func _cmd_reload_scene(params: Dictionary) -> Dictionary:
	var scene_path := str(params.get("scene_path", ""))
	if scene_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "scene_path is required.")
	# confirm is a server-side safety gate; we honor it defensively addon-side too.
	if not params.get("confirm", false):
		return _router._fail("PRECONDITION_FAILED", "This call discards unsaved changes. Set confirm=True to proceed.", "confirm")
	var open_paths: PackedStringArray = EditorInterface.get_open_scenes()
	var is_open := false
	for p in open_paths:
		if str(p) == scene_path:
			is_open = true
			break
	if not is_open:
		return _router._fail("PRECONDITION_FAILED", "Scene '%s' is not open. Open it first." % scene_path, "open_scene")
	EditorInterface.reload_scene_from_path(scene_path)
	return _router._ok({"scene_path": scene_path, "reloaded": true})



func _cmd_save_all_scenes(_params: Dictionary) -> Dictionary:
	EditorInterface.save_all_scenes()
	var count := EditorInterface.get_open_scenes().size()
	return _router._ok({"saved": true, "count": count})



func _cmd_list_open_scenes(_params: Dictionary) -> Dictionary:
	var paths: PackedStringArray = EditorInterface.get_open_scenes()
	var scenes: Array = []
	for p in paths:
		scenes.append({"path": str(p)})
	return _router._ok({"scenes": scenes})



func _cmd_select_nodes(params: Dictionary) -> Dictionary:
	var raw_paths: Variant = params.get("node_paths", [])
	if raw_paths is String:
		return _router._fail("VALIDATION_ERROR", "node_paths must be an array of scene-relative paths.")
	var node_paths: Array = raw_paths as Array
	if node_paths.is_empty():
		return _router._fail("VALIDATION_ERROR", "Provide at least one node path in node_paths.")
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var selection := EditorInterface.get_selection()
	selection.clear()
	var selected: Array = []
	for raw_path in node_paths:
		var path_str := Inspect.normalize_node_path(str(raw_path))
		var node := root.get_node_or_null(NodePath(path_str))
		if node == null:
			return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % path_str)
		selection.add_node(node)
		selected.append(path_str)
	var scene_path := root.scene_file_path if not root.scene_file_path.is_empty() else ""
	return _router._ok({"scene_path": scene_path, "selected": selected, "count": selected.size()})



func _cmd_instance_scene(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var parent_path := str(params.get("parent_path", "."))
	if parent_path.begins_with("/"):
		parent_path = parent_path.substr(1)
	if parent_path.is_empty():
		parent_path = "."
	var parent: Node = root.get_node_or_null(NodePath(parent_path))
	if parent == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % parent_path)

	var scene_path := str(params.get("scene_path", ""))
	if not FileAccess.file_exists(scene_path):
		return _router._fail("RESOURCE_NOT_FOUND", "No scene at '%s'." % scene_path)
	var packed: PackedScene = load(scene_path)
	if packed == null:
		return _router._fail("VALIDATION_ERROR", "Failed to load PackedScene from '%s'." % scene_path)

	var instance: Node = packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	var custom_name := str(params.get("name", ""))
	if not custom_name.is_empty():
		instance.name = custom_name
	# #477 (parent rule): instancing under a non-editable instanced child applies
	# live but the whole new instance is lost on save.
	var persistence := _router._helpers.persistent_target(parent)
	var ur := EditorInterface.get_editor_undo_redo()
	ur.create_action("Instance %s" % scene_path.get_file())
	ur.add_do_method(parent, "add_child", instance)
	ur.add_do_method(instance, "set_owner", root)
	ur.add_do_reference(instance)
	ur.add_undo_method(parent, "remove_child", instance)
	ur.commit_action()
	return _router._ok(_router._helpers.with_persistence({
		"node_path": Inspect.relative_path(instance, root),
		"scene_path": scene_path,
		"instanced": true,
	}, persistence))



## Extract the subtree at `node_path` into a reusable .tscn prefab (issue #531),
## optionally replacing it with an instance of the new scene — the editor's own
## "Save Branch as Scene" move, driven from the bridge.
##
## Honesty rules the handler enforces before any mutation:
## - The subtree must be owned by the edited scene (owner == edited root, like the
##   #473 rename refusal): nodes from another scene (or an inherited base) are
##   refused with a hint naming the source scene, never silently partially packed.
## - The destination must not already exist (ResourceSaver would overwrite).
## - `preview=true` (the dry-run) runs the same refusals + counts the nodes the
##   real run would extract, and mutates nothing — a preview that would succeed
##   and then fail for real is a lie.
##
## replace_with_instance commits ONE UndoRedo action (remove original + add the
## instanced .tscn in place), so undo restores the original subtree wholesale.
## save_current saves the edited scene after the extract (prefab + tree on disk
## together). The persistence verdict keys on the subtree root (#477 family).
func _cmd_extract_scene(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var node_path := Inspect.normalize_node_path(str(params.get("node_path", "")))
	var scene_path := str(params.get("scene_path", ""))
	var replace := bool(params.get("replace_with_instance", false))
	var save_current := bool(params.get("save_current", false))
	var preview := bool(params.get("preview", false))
	if node_path.is_empty() or scene_path.is_empty():
		return _router._fail("VALIDATION_ERROR", "'node_path' and 'scene_path' are required.")
	if not scene_path.begins_with("res://") or not scene_path.ends_with(".tscn"):
		return _router._fail("VALIDATION_ERROR", "'scene_path' must be a res:// path ending in .tscn.", "scene_path")
	var node: Node = root.get_node_or_null(NodePath(node_path))
	if node == null:
		return _router._fail("RESOURCE_NOT_FOUND", "No node at '%s'." % node_path)
	# #477 honesty: refuse subtrees the edited scene does not own. Packing them
	# produces a .tscn, but the replace-with-instance drop (and any unsaved
	# original) would be a silent half-failure — same family as the rename refusal.
	# A null owner on a non-root node is an unowned editor artifact (@tool-script
	# add): it is never saved, so extraction would pack a phantom — refuse it too.
	if node != root:
		if node.owner == null:
			return _router._fail(
				"VALIDATION_ERROR",
				"Node '%s' has no owner in the edited scene (e.g. it was added by a @tool script), so it is not saved — extracting it would produce a prefab of a node that vanishes on reload. Save it first (set its owner), then extract." % root.get_path_to(node),
				"node_path",
			)
		if node.owner != root and not root.is_editable_instance(node.owner):
			var source := str(node.owner.scene_file_path)
			if source.is_empty():
				source = "the edited scene's root"
			return _router._fail(
				"VALIDATION_ERROR",
				"Node '%s' comes from the instanced scene '%s' (Editable Children is off) — extracting it would silently drop those nodes on save. Open '%s' and extract there, or enable Editable Children first." % [root.get_path_to(node), source, source],
				"node_path",
			)
		if node.owner == root and _has_foreign_owned_child(node, root):
			return _router._fail(
				"VALIDATION_ERROR",
				"The subtree at '%s' contains nodes owned by an instanced child scene — extracting it would pack a mixed-ownership prefab. Enable Editable Children on that instance and flatten it first, or extract a fully scene-owned subtree." % root.get_path_to(node),
				"node_path",
			)
	if FileAccess.file_exists(scene_path):
		return _router._fail(
			"VALIDATION_ERROR",
			"A scene already exists at '%s'. Pick another destination (or delete the existing file first)." % scene_path,
			"scene_path",
		)
	var node_count := _count_subtree(node)
	if preview:
		# Read-only preview: the refusals ran above; report what WOULD happen.
		var preview_persistence := _router._helpers.persistent_target(node)
		return _router._ok(_router._helpers.with_persistence({
			"node_path": root.get_path_to(node),
			"scene_path": scene_path,
			"extracted": false,
			"replaced": false,
			"saved": false,
			"node_count": node_count,
		}, preview_persistence))
	# Pack a detached duplicate so the original tree is untouched if the save fails.
	var packed: PackedScene = PackedScene.new()
	var duplicate := node.duplicate()
	if node != root:
		_reown_subtree(duplicate, duplicate)
	var pack_err := packed.pack(duplicate)
	duplicate.free()
	if pack_err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to pack the subtree at '%s' (error %d)." % [root.get_path_to(node), pack_err])
	var save_err := ResourceSaver.save(packed, scene_path)
	if save_err != OK:
		return _router._fail("INTERNAL_ERROR", "Failed to save the prefab to '%s' (error %d)." % [scene_path, save_err])
	EditorInterface.get_resource_filesystem().scan()
	EditorInterface.get_resource_filesystem().update_file(scene_path)

	var persistence := _router._helpers.persistent_target(node)
	var instance_path := ""
	if replace:
		var parent := node.get_parent()
		if parent == null:
			return _router._fail("INTERNAL_ERROR", "The subtree root has no parent; it cannot be replaced with an instance.")
		var packed_scene: PackedScene = load(scene_path)
		if packed_scene == null:
			return _router._fail("INTERNAL_ERROR", "The prefab at '%s' could not be reloaded for instancing." % scene_path)
		var instance: Node = packed_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
		instance.name = node.name
		var index := node.get_index()
		var ur := EditorInterface.get_editor_undo_redo()
		ur.create_action("Extract %s as %s" % [node.name, scene_path.get_file()])
		ur.add_do_method(parent, "remove_child", node)
		ur.add_do_method(parent, "add_child", instance)
		ur.add_do_method(parent, "move_child", instance, index)
		ur.add_do_method(instance, "set_owner", root)
		ur.add_do_reference(instance)
		ur.add_undo_method(parent, "remove_child", instance)
		ur.add_undo_method(parent, "add_child", node)
		ur.add_undo_method(parent, "move_child", node, index)
		ur.add_undo_method(node, "set_owner", node.owner)
		ur.commit_action()
		instance_path = Inspect.relative_path(instance, root)
	if save_current:
		EditorInterface.save_scene()
	return _router._ok(_router._helpers.with_persistence({
		"node_path": root.get_path_to(node),
		"scene_path": scene_path,
		"extracted": true,
		"replaced": replace,
		"saved": save_current,
		"node_count": node_count,
		"instance_path": instance_path,
	}, persistence))


## True when any node strictly inside `node`'s subtree (children down, not the
## node itself) is owned by something other than `owner` — i.e. part of the
## subtree belongs to an instanced child scene (#477 family). The subtree root's
## own ownership was already checked by the caller.
func _has_foreign_owned_child(node: Node, owner: Node) -> bool:
	for child in node.get_children():
		if child.owner != owner:
			return true
		if _has_foreign_owned_child(child, owner):
			return true
	return false


## Count the subtree rooted at `node` (itself included) for the result/preview.
func _count_subtree(node: Node) -> int:
	var count := 1
	for child in node.get_children():
		count += _count_subtree(child)
	return count


## Point every node in the duplicated subtree at `new_root` so PackedScene.pack()
## serializes the whole subtree (pack() only writes nodes owned by the pack root).
func _reown_subtree(node: Node, new_root: Node) -> void:
	node.owner = new_root
	for child in node.get_children():
		_reown_subtree(child, new_root)




## Trigger EditorFileSystem.scan() so external file edits (made by non-editor
## tools: other agents, scripts, git operations) are picked up (issue #486).
## Non-destructive: a scan reads the disk and refreshes the editor's view — it
## discards no editor state (unlike reload_scene, which discards unsaved changes
## and is confirm-gated). The scan is asynchronous: `scanning` in the response
## reports whether it is still in flight; the #459/#453 read-side (`scanning`
## on cmd_get_import_status, the parse-check gate) keys on the same state.
func _cmd_rescan_filesystem(_params: Dictionary) -> Dictionary:
	var fs := EditorInterface.get_resource_filesystem()
	fs.scan()
	return _router._ok({"scanned": true, "scanning": fs.is_scanning()})
