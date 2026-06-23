@tool
class_name MCPVisualShaderRead
extends RefCounted
## Pure, read-only serialization of a VisualShader node graph (issue #219 G6 — rollback
## enabler). Takes a VisualShader resource (never EditorInterface), so verifiable
## headlessly (see godot/tests/visual_shader_read_smoke.gd). Inverts
## create_visual_shader / add_shader_node / connect_shader_nodes / set_shader_node_param.

const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")

const _MODE_NAMES := {
	VisualShader.MODE_SPATIAL: "spatial",
	VisualShader.MODE_CANVAS_ITEM: "canvas_item",
	VisualShader.MODE_PARTICLES: "particles",
	VisualShader.MODE_SKY: "sky",
	VisualShader.MODE_FOG: "fog",
}


## { mode, nodes:[{id, type, position:{x,y}, parameters:{...}}],
##   connections:[{from_node, from_port, to_node, to_port}] }.
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
	}
