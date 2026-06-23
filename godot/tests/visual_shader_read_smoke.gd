@tool
extends SceneTree
## Headless behavior test for MCPVisualShaderRead (issue #219 G6).
##
## Run via: godot --headless --path godot/ --script res://tests/visual_shader_read_smoke.gd
## Builds a real VisualShader graph (no EditorInterface) the same way the writers do —
## add_node(int(mode), ...) + connect_nodes — and verifies the pure read serialization
## against the live Godot API.

const VisualShaderRead := preload("res://addons/godot_mcp/visual_shader_read.gd")


func _initialize() -> void:
	var failures: Array[String] = []

	var shader := VisualShader.new()
	shader.set_mode(VisualShader.MODE_CANVAS_ITEM)
	var type := int(shader.get_mode())  # mirror the writers' Type-from-Mode convention

	# Add a color-constant node (id 2) and wire it to the output node (id 0, port 0).
	var color := VisualShaderNodeColorConstant.new()
	color.constant = Color(1, 0, 0, 1)
	shader.add_node(type, color, Vector2(-200, 40), 2)
	shader.connect_nodes(type, 2, 0, 0, 0)

	var data: Dictionary = VisualShaderRead.serialize(shader)
	_eq(failures, "mode", data.get("mode"), "canvas_item")

	var nodes: Array = data["nodes"]
	var ids: Array = []
	for n in nodes:
		ids.append(n["id"])
	if not (ids.has(0) and ids.has(2)):
		failures.append("expected node ids 0 and 2, got %s" % str(ids))
	var color_node: Dictionary = {}
	for n in nodes:
		if n["id"] == 2:
			color_node = n
	_eq(failures, "color.type", color_node.get("type"), "VisualShaderNodeColorConstant")
	_eq(failures, "color.position", color_node.get("position"), {"x": -200.0, "y": 40.0})
	var params: Dictionary = color_node.get("parameters", {})
	if not params.has("constant"):
		failures.append("color node parameters missing 'constant': %s" % str(params.keys()))

	var connections: Array = data["connections"]
	if connections.size() != 1:
		failures.append("expected 1 connection, got %s" % str(connections))
	else:
		var edge: Dictionary = connections[0]
		_eq(failures, "edge.from_node", edge.get("from_node"), 2)
		_eq(failures, "edge.to_node", edge.get("to_node"), 0)

	# Output must be JSON-safe.
	if JSON.stringify(data) == "":
		failures.append("serialized graph is not JSON-safe")

	if failures.is_empty():
		print("VISUAL_SHADER_READ_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("VISUAL_SHADER_READ_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])
