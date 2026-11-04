@tool
class_name MCPVisualShaderRead
extends RefCounted
## Pure, read-only serialization of a VisualShader node graph (issue #219 G6 — rollback
## enabler). Takes a VisualShader resource (never EditorInterface), so verifiable
## headlessly (see godot/tests/visual_shader_read_smoke.gd). Inverts
## create_visual_shader / add_shader_node / connect_shader_nodes / set_shader_node_param.

const Inspect := preload("./scene_inspect.gd")
const Coerce := preload("./type_coerce.gd")

const _MODE_NAMES := {
	VisualShader.MODE_SPATIAL: "spatial",
	VisualShader.MODE_CANVAS_ITEM: "canvas_item",
	VisualShader.MODE_PARTICLES: "particles",
	VisualShader.MODE_SKY: "sky",
	VisualShader.MODE_FOG: "fog",
}


## { mode, nodes:[{id, type, position:{x,y}, parameters:{...}}],
##   connections:[{from_node, from_port, to_node, to_port}],
##   groups:[{node_id, name, members:[{id, type, position, parameters, group}]}] }.
##
## The writers add nodes under int(shader.get_mode()) as the VisualShader.Type arg, so the
## read enumerates against that same value to round-trip (see handlers/visual_shader.gd).
static func serialize(shader: VisualShader) -> Dictionary:
	var type := int(shader.get_mode())
	var nodes: Array = []
	for id in shader.get_node_list(type):
		var node: VisualShaderNode = shader.get_node(type, id)
		nodes.append({
			"id": int(id),
			"type": node.get_class(),
			"position": Coerce.to_json(shader.get_node_position(type, id)),
			"parameters": Inspect.resource_properties(node),
		})
	var connections: Array = []
	for c in shader.get_node_connections(type):
		connections.append({
			"from_node": int(c["from_node"]),
			"from_port": int(c["from_port"]),
			"to_node": int(c["to_node"]),
			"to_port": int(c["to_port"]),
		})
	return {
		"mode": _MODE_NAMES.get(int(shader.get_mode()), "spatial"),
		"nodes": nodes,
		"connections": connections,
		"groups": _serialize_groups(shader, type),
	}


## One entry per group node (issue #601): its node id in the shader, its name, and
## the nodes in its internal graph. VisualShaderNodeGroup is 4.8+; the ClassDB
## gate keeps this file parsing and group-less on the 4.4–4.7 floor.
static func _serialize_groups(shader: VisualShader, type: int) -> Array:
	var groups: Array = []
	if not ClassDB.class_exists("VisualShaderNodeGroup"):
		return groups
	for id in shader.get_node_list(type):
		var node: VisualShaderNode = shader.get_node(type, id)
		if node == null or not node.has_method("get_group"):
			continue
		var group: Variant = node.call("get_group")
		if not (group is Resource):
			continue
		groups.append({
			"node_id": int(id),
			"name": str(group.call("get_group_name")),
			"members": _serialize_group_members(group, int(id)),
		})
	return groups


static func _serialize_group_members(group: Resource, group_node_id: int) -> Array:
	var members: Array = []
	for id in group.call("get_node_list"):
		var node: VisualShaderNode = group.call("get_node", int(id))
		if node == null:
			continue
		members.append({
			"id": int(id),
			"type": node.get_class(),
			"position": Coerce.to_json(group.call("get_node_position", int(id))),
			"parameters": Inspect.resource_properties(node),
			"group": group_node_id,
		})
	return members
