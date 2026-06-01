@tool
class_name MCPSceneInspect
extends RefCounted
## Pure, read-only serialization of scene/node state (issue #5).
##
## These helpers take Nodes (never EditorInterface), so they are verifiable
## headlessly (see godot/tests/inspect_smoke.gd). All output is JSON-safe via
## MCPTypeCoerce. The cmd_* handlers supply the editor-provided nodes.

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")


## Recursive { name, type, script, children } for a subtree.
## max_depth < 0 is unlimited; max_depth == 0 returns the node with no children.
static func serialize_tree(node: Node, max_depth: int = -1) -> Dictionary:
	var data: Dictionary = {
		"name": String(node.name),
		"type": node.get_class(),
		"script": script_path(node),
	}
	var children: Array = []
	if max_depth != 0:
		var child_depth: int = (max_depth - 1) if max_depth > 0 else -1
		for child in node.get_children():
			children.append(serialize_tree(child, child_depth))
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


## The attached script's resource path, or null when there is none.
static func script_path(node: Node) -> Variant:
	var script: Variant = node.get_script()
	if script is Script and not script.resource_path.is_empty():
		return script.resource_path
	return null


static func relative_path(node: Node, scene_root: Node) -> String:
	if node == scene_root:
		return "."
	return String(scene_root.get_path_to(node))
