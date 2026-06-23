@tool
class_name MCPSceneInspect
extends RefCounted
## Pure, read-only serialization of scene/node state (issue #5).
##
## These helpers take Nodes (never EditorInterface), so they are verifiable
## headlessly (see godot/tests/inspect_smoke.gd). All output is JSON-safe via
## MCPTypeCoerce. The cmd_* handlers supply the editor-provided nodes.

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")


## Recursive { name, type, path, script, children } for a subtree.
## max_depth < 0 is unlimited; max_depth == 0 returns the node with no children.
## Every node carries an explicit scene-relative `path` (#180) — "." for the scene
## root, e.g. "Player/Weapon" below it — in exactly the form the path-taking tools
## accept, so clients never have to reconstruct paths by walking the tree.
## lightweight (#168) drops the `script` field (skips the per-node get_script call)
## for a smaller discovery payload — { name, type, path, children } only.
## scene_root threads the root down the recursion; it defaults to `node` (the top
## call passes the root), so existing 1-3 arg callers keep working.
static func serialize_tree(
	node: Node, max_depth: int = -1, lightweight: bool = false, scene_root: Node = null
) -> Dictionary:
	var root: Node = scene_root if scene_root != null else node
	var data: Dictionary = {
		"name": String(node.name),
		"type": node.get_class(),
		"path": relative_path(node, root),
	}
	if not lightweight:
		data["script"] = script_path(node)
	var children: Array = []
	if max_depth != 0:
		var child_depth: int = (max_depth - 1) if max_depth > 0 else -1
		for child in node.get_children():
			children.append(serialize_tree(child, child_depth, lightweight, root))
	data["children"] = children
	return data


## { node_path, type, script, properties, children:[names] } for one node,
## with node_path relative to scene_root ("." for the root itself).
static func node_info(node: Node, scene_root: Node) -> Dictionary:
	var child_names: Array = []
	for child in node.get_children():
		child_names.append(String(child.name))
	return {
		"node_path": relative_path(node, scene_root),
		"type": node.get_class(),
		"script": script_path(node),
		"properties": node_properties(node),
		"children": child_names,
	}


## Exported / script-declared properties, JSON-coerced.
static func node_properties(node: Node) -> Dictionary:
	var props: Dictionary = {}
	for entry in node.get_property_list():
		if (entry.get("usage", 0) & PROPERTY_USAGE_SCRIPT_VARIABLE) != 0:
			var name: String = entry["name"]
			props[name] = Coerce.to_json(node.get(name))
	return props


## Read one property by name — built-in OR script var, no usage filter (issue #215).
## { value, exists }: exists=false (value=null) when the node has no such property,
## so a real null value is distinguishable from "absent". JSON-coerced via type_coerce.
static func read_property(node: Node, property: String) -> Dictionary:
	for entry in node.get_property_list():
		if String(entry.get("name", "")) == property:
			return {"value": Coerce.to_json(node.get(property)), "exists": true}
	return {"value": null, "exists": false}


## A node's group memberships as plain strings, sorted, excluding editor-internal
## groups (names beginning with "_") — issue #216. Inverts add/remove_from_group.
static func node_groups(node: Node) -> Array:
	var out: Array = []
	for g in node.get_groups():
		var name := String(g)
		if not name.begins_with("_"):
			out.append(name)
	out.sort()
	return out


## A resource's editable+stored properties, JSON-coerced (issue #34). Unlike nodes
## (script vars), built-in resource fields are EDITOR|STORAGE, so filter on those and
## drop the base Resource bookkeeping fields.
static func resource_properties(res: Resource) -> Dictionary:
	const _SKIP := ["resource_local_to_scene", "resource_name", "resource_path", "script"]
	var props: Dictionary = {}
	for entry in res.get_property_list():
		var usage := int(entry.get("usage", 0))
		if (usage & PROPERTY_USAGE_EDITOR) == 0 or (usage & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var name: String = entry["name"]
		if name in _SKIP:
			continue
		props[name] = Coerce.to_json(res.get(name))
	return props


## The attached script's resource path, or null when there is none.
static func script_path(obj: Object) -> Variant:
	var script: Variant = obj.get_script()
	if script is Script and not script.resource_path.is_empty():
		return script.resource_path
	return null


static func relative_path(node: Node, scene_root: Node) -> String:
	if node == scene_root:
		return "."
	return String(scene_root.get_path_to(node))
