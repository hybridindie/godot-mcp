@tool
class_name MCPCompositeHandlers
extends RefCounted
const Coerce := preload("../type_coerce.gd")
## Domain handler: composite/macro tools (issue #154).
##
## Each handler collapses a multi-step scene edit into ONE UndoRedo action and a
## single bridge round-trip. Registered by the router on _init().

const Inspect := preload("../scene_inspect.gd")

var _router: MCPCommandRouter


func _init(router: MCPCommandRouter) -> void:
	_router = router


func register(handlers: Dictionary) -> void:
	handlers["cmd_compose_node"] = _cmd_compose_node
	handlers["cmd_batch_create_nodes"] = _cmd_batch_create_nodes
	handlers["cmd_apply_node_edits"] = _cmd_apply_node_edits


# -- helpers -----------------------------------------------------------------

## Instantiate `node_type`, set `name`, apply `properties`, attach `script_path` —
## all directly on the fresh (detached) instance before it enters the tree.
## Returns {"node": Node, "properties_set": Array} on success, or a structured
## error Dictionary (carrying "ok": false) which the caller forwards as-is.
func _build_node(
	node_type: String, node_name: String, properties: Dictionary, script_path: String
) -> Dictionary:
	if not ClassDB.class_exists(node_type) or not ClassDB.can_instantiate(node_type):
		return _router._fail(
			"VALIDATION_ERROR", "Unknown or non-instantiable node type '%s'." % node_type
		)
	var node: Node = ClassDB.instantiate(node_type)
	node.name = node_name
	var set_names: Array = []
	for prop in properties:
		var prop_name := str(prop)
		var prop_type := _router._helpers.property_type(node, prop_name)
		if prop_type == -1:
			node.free()
			return _router._fail(
				"VALIDATION_ERROR", "'%s' has no property '%s'." % [node_type, prop_name]
			)
		node.set(prop_name, Coerce.from_json(properties[prop], prop_type))
		set_names.append(prop_name)
	if not script_path.is_empty():
		if not ResourceLoader.exists(script_path):
			node.free()
			return _router._fail("RESOURCE_NOT_FOUND", "No script at '%s'." % script_path)
		var script: Variant = load(script_path)
		if not (script is Script):
			node.free()
			return _router._fail("VALIDATION_ERROR", "'%s' is not a script resource." % script_path)
		node.set_script(script)
	return {"node": node, "properties_set": set_names}


func _maybe_save(params: Dictionary) -> bool:
	if not bool(params.get("save", false)):
		return false
	return EditorInterface.save_scene() == OK


# -- handlers ----------------------------------------------------------------

func _cmd_compose_node(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var parent_found := _router._resolve(params.get("parent_path", "."))
	if not parent_found["ok"]:
		return parent_found
	var parent: Node = parent_found["node"]

	var built := _build_node(
		str(params.get("node_type", "")),
		str(params.get("name", "")),
		params.get("properties", {}),
		str(params.get("script_path", "")),
	)
	if built.has("ok"):
		return built  # structured error
	var node: Node = built["node"]

	# Children are parented to the new node before it enters the tree; freeing
	# `node` on a later error cascades to them, so no separate cleanup is needed.
	var child_names: Array = []
	var child_nodes: Array = []
	for child in params.get("children", []):
		var child_built := _build_node(
			str(child.get("node_type", "")),
			str(child.get("name", "")),
			child.get("properties", {}),
			str(child.get("script_path", "")),
		)
		if child_built.has("ok"):
			node.free()
			return child_built
		var child_node: Node = child_built["node"]
		node.add_child(child_node)
		child_nodes.append(child_node)

	# #477 (parent rule): a composed node under a non-editable instanced parent
	# (and its whole subtree) is lost on save. #528: one shared commit — the
	# N-child variant with whole-subtree ownership inside the same action (the
	# undo side removes the subtree root, which drops the whole subtree).
	var persistence := _router._helpers.persistent_target(parent)
	var paths: Array = _router._helpers.commit_add_children(
		parent, [node], "Compose %s" % node.name, true
	)
	var node_path: String = paths[0]

	for child_node in child_nodes:
		child_names.append(String(child_node.name))
	return _router._ok(_router._helpers.with_persistence({
		"node_path": node_path,
		"created": true,
		"children": child_names,
		"script_attached": not str(params.get("script_path", "")).is_empty(),
		"properties_set": built["properties_set"],
		"saved": _maybe_save(params),
	}, persistence))


func _cmd_batch_create_nodes(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var parent_found := _router._resolve(params.get("parent_path", "."))
	if not parent_found["ok"]:
		return parent_found
	var parent: Node = parent_found["node"]
	var node_type := str(params.get("node_type", ""))
	var names: Array = params.get("names", [])
	if names.is_empty():
		return _router._fail("VALIDATION_ERROR", "'names' must be a non-empty array.")
	var properties: Dictionary = params.get("properties", {})

	var nodes: Array = []
	for raw_name in names:
		var built := _build_node(node_type, str(raw_name), properties, "")
		if built.has("ok"):
			for created_node in nodes:
				created_node.free()
			return built
		nodes.append(built["node"])

	# #477 (parent rule): batch-created nodes under a non-editable instanced
	# parent are all lost on save — one verdict covers them (they share the
	# parent); a per-node verdict would repeat the same token.
	var persistence := _router._helpers.persistent_target(parent)
	# Dry-run defense-in-depth (PR #545 review): the MCP layer enforces preview
	# semantics (run_or_preview never sends this command with dry_run set), but
	# a raw envelope carrying dry_run: true must not mutate the tree either —
	# the batch_set_property handler honors the flag the same way.
	if bool(params.get("dry_run", false)):
		var planned: Array = []
		for node in nodes:
			planned.append(Inspect.relative_path(node, root))
		return _router._ok({
			"created": [],
			"count": planned.size(),
			"saved": false,
			"dry_run": true,
			"undoable": _router._helpers.undoable_for_count(names.size()),
			"hint": "" if _router._helpers.undoable_for_count(names.size()) else _router._helpers.undo_threshold_hint(names.size()),
		})
	# #523: batch creates share the UndoRedo threshold — the decision + hint
	# live on the router (one site), same honesty shape as batch_set_property.
	var undoable := _router._helpers.undoable_for_count(names.size())
	if not undoable:
		for node in nodes:
			parent.add_child(node)
			node.set_owner(root)
	else:
		# #528: one shared N-child commit (one undo action for the batch).
		_router._helpers.commit_add_children(parent, nodes, "Batch create %d %s" % [nodes.size(), node_type])

	var created: Array = []
	for node in nodes:
		created.append(Inspect.relative_path(node, root))
	return _router._ok(_router._helpers.with_persistence({
		"created": created,
		"count": created.size(),
		"saved": _maybe_save(params),
		"undoable": undoable,
		"hint": "" if undoable else _router._helpers.undo_threshold_hint(names.size()),
	}, persistence))


func _cmd_apply_node_edits(params: Dictionary) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _router._fail("PRECONDITION_FAILED", "No scene is open.", "active_scene")
	var edits: Array = params.get("edits", [])
	if edits.is_empty():
		return _router._fail("VALIDATION_ERROR", "'edits' must be a non-empty array.")

	var to_apply: Array = []  # each: {node, property, value, old}
	var edited_paths: Array = []
	var skipped: Array = []
	var persistence: Array = []  # #477: one verdict per edited node (#528: shared helper)
	var verdict_nodes: Array = []
	var verdict_paths: Array = []
	for edit in edits:
		var found := _router._resolve(edit.get("node_path", ""))
		if not found["ok"]:
			return found  # a specific bad path is a hard error
		var node: Node = found["node"]
		var properties: Dictionary = edit.get("properties", {})
		var applied_any := false
		for prop in properties:
			var prop_name := str(prop)
			var prop_type := _router._helpers.property_type(node, prop_name)
			if prop_type == -1:
				skipped.append({
					"node_path": str(edit.get("node_path")),
					"property": prop_name,
					"reason": "no such property",
				})
				continue
			to_apply.append({
				"node": node,
				"property": prop_name,
				"value": Coerce.from_json(properties[prop], prop_type),
				"old": node.get(prop_name),
			})
			applied_any = true
		if applied_any:
			var node_path := Inspect.relative_path(node, root)
			edited_paths.append(node_path)
			# #477: each edited node gets its own verdict — one aggregate ok
			# must never hide a target the save drops. Stamped by the shared
			# helper (#528).
			verdict_nodes.append(node)
			verdict_paths.append(node_path)
	persistence = _router._helpers.persistence_entries(verdict_nodes, verdict_paths)

	# Dry-run defense-in-depth (PR #545 review): the MCP layer enforces preview
	# semantics (run_or_preview never sends this command with dry_run set), but
	# a raw envelope carrying dry_run: true must not mutate the tree either.
	if bool(params.get("dry_run", false)):
		return _router._ok({
			"edited": [],
			"skipped": skipped,
			"count": 0,
			"saved": false,
			"dry_run": true,
			"undoable": _router._helpers.undoable_for_count(to_apply.size()),
			"hint": "" if _router._helpers.undoable_for_count(to_apply.size()) else _router._helpers.undo_threshold_hint(to_apply.size(), "applies"),
			"persistence": persistence,
		})

	if not to_apply.is_empty():
		# #523: per-node property edits share the UndoRedo threshold — the
		# decision + hint live on the router (one site), same honesty shape as
		# batch_set_property.
		var undoable := _router._helpers.undoable_for_count(to_apply.size())
		if not undoable:
			for item in to_apply:
				item["node"].set(item["property"], item["value"])
		else:
			var undo_redo := EditorInterface.get_editor_undo_redo()
			undo_redo.create_action("Apply %d node edits" % to_apply.size())
			for item in to_apply:
				undo_redo.add_do_property(item["node"], item["property"], item["value"])
				undo_redo.add_undo_property(item["node"], item["property"], item["old"])
			undo_redo.commit_action()
		for item in to_apply:
			_router._helpers.invalidate_prop_cache(item["node"])

	return _router._ok({
		"edited": edited_paths,
		"skipped": skipped,
		"count": edited_paths.size(),
		"saved": _maybe_save(params),
		"undoable": _router._helpers.undoable_for_count(to_apply.size()),
		"hint": "" if _router._helpers.undoable_for_count(to_apply.size()) else _router._helpers.undo_threshold_hint(to_apply.size(), "applies"),
		"persistence": persistence,
	})
