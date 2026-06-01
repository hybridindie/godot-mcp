@tool
extends SceneTree
## Headless behavior test for the read-only inspection serializers (issue #5).
##
## Run via: godot --headless --path godot/ --script res://tests/inspect_smoke.gd
## Exercises the pure, editor-independent helpers MCPTypeCoerce and
## MCPSceneInspect — JSON-safe type coercion, recursive scene serialization, and
## max_depth — without EditorInterface. The editor glue in the cmd_* handlers is
## covered by the cross-process e2e test (test_inspection_e2e.py).

const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")
const Inspect := preload("res://addons/godot_mcp/scene_inspect.gd")
const Probe := preload("res://tests/fixtures/probe.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	_test_type_coerce(failures)
	_test_from_json(failures)
	_test_serialize_tree(failures)
	_test_node_properties(failures)
	_test_node_info(failures)

	if failures.is_empty():
		print("INSPECT_TEST_OK")
		quit(0)
	else:
		for f in failures:
			printerr("FAIL: %s" % f)
		print("INSPECT_TEST_FAIL")
		quit(1)


func _eq(failures: Array[String], label: String, got: Variant, want: Variant) -> void:
	if got != want:
		failures.append("%s: expected %s, got %s" % [label, str(want), str(got)])


func _test_type_coerce(failures: Array[String]) -> void:
	_eq(failures, "vector2", Coerce.to_json(Vector2(1, 2)), {"x": 1.0, "y": 2.0})
	_eq(failures, "vector3", Coerce.to_json(Vector3(1, 2, 3)), {"x": 1.0, "y": 2.0, "z": 3.0})
	_eq(failures, "color", Coerce.to_json(Color(1, 0, 0, 1)), {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0})
	_eq(failures, "nodepath", Coerce.to_json(NodePath("a/b")), "a/b")
	_eq(failures, "array", Coerce.to_json([Vector2(0, 0), 5]), [{"x": 0.0, "y": 0.0}, 5])
	_eq(failures, "dict", Coerce.to_json({"v": Vector2(1, 1)}), {"v": {"x": 1.0, "y": 1.0}})
	# Primitives pass through unchanged.
	_eq(failures, "int", Coerce.to_json(42), 42)
	_eq(failures, "string", Coerce.to_json("hi"), "hi")
	_eq(failures, "bool", Coerce.to_json(true), true)
	_eq(failures, "null", Coerce.to_json(null), null)
	# A path-less Resource coerces to its class name, never str() instance details.
	_eq(failures, "resource_classname", Coerce.to_json(Resource.new()), "Resource")


func _test_from_json(failures: Array[String]) -> void:
	# Dict form (symmetric with to_json) and array form both coerce.
	_eq(failures, "fj.vector2.dict", Coerce.from_json({"x": 1, "y": 2}, TYPE_VECTOR2), Vector2(1, 2))
	_eq(failures, "fj.vector2.arr", Coerce.from_json([1, 2], TYPE_VECTOR2), Vector2(1, 2))
	_eq(failures, "fj.vector3", Coerce.from_json({"x": 1, "y": 2, "z": 3}, TYPE_VECTOR3), Vector3(1, 2, 3))
	_eq(failures, "fj.color", Coerce.from_json({"r": 1, "g": 0, "b": 0, "a": 1}, TYPE_COLOR), Color(1, 0, 0, 1))
	_eq(failures, "fj.nodepath", Coerce.from_json("a/b", TYPE_NODE_PATH), NodePath("a/b"))
	_eq(failures, "fj.int", Coerce.from_json(5, TYPE_INT), 5)
	_eq(failures, "fj.float", Coerce.from_json(2.5, TYPE_FLOAT), 2.5)
	_eq(failures, "fj.bool", Coerce.from_json(true, TYPE_BOOL), true)
	_eq(failures, "fj.string", Coerce.from_json("hi", TYPE_STRING), "hi")
	# Round-trips through to_json.
	_eq(failures, "fj.roundtrip", Coerce.from_json(Coerce.to_json(Vector2(3, 4)), TYPE_VECTOR2), Vector2(3, 4))
	var rect: Variant = Coerce.from_json({"position": [0, 0], "size": [4, 5]}, TYPE_RECT2)
	_eq(failures, "fj.rect2", rect, Rect2(0, 0, 4, 5))
	# Malformed Rect2 input must not crash; it degrades to a default.
	_eq(failures, "fj.rect2.bad", Coerce.from_json("oops", TYPE_RECT2), Rect2())


func _test_serialize_tree(failures: Array[String]) -> void:
	var world := Node2D.new()
	world.name = "World"
	var sprite := Sprite2D.new()
	sprite.name = "Sprite"
	var deep := Node.new()
	deep.name = "Deep"
	world.add_child(sprite)
	sprite.add_child(deep)

	var full: Dictionary = Inspect.serialize_tree(world)
	_eq(failures, "tree.name", full.get("name"), "World")
	_eq(failures, "tree.type", full.get("type"), "Node2D")
	_eq(failures, "tree.script", full.get("script"), null)
	var children: Array = full.get("children")
	if children.size() != 1 or children[0].get("name") != "Sprite":
		failures.append("tree children wrong: %s" % str(children))
	elif children[0].get("children")[0].get("name") != "Deep":
		failures.append("tree grandchild wrong")

	# max_depth=1 ⇒ root + immediate children, but their children truncated.
	var shallow: Dictionary = Inspect.serialize_tree(world, 1)
	var shallow_children: Array = shallow.get("children")
	_eq(failures, "depth1.child", shallow_children[0].get("name"), "Sprite")
	_eq(failures, "depth1.truncated", shallow_children[0].get("children"), [])

	# Output must be JSON-safe (stringify must not error).
	if JSON.stringify(full) == "":
		failures.append("serialized tree is not JSON-safe")

	world.free()


func _test_node_properties(failures: Array[String]) -> void:
	var node := Node2D.new()
	node.set_script(Probe)
	var props: Dictionary = Inspect.node_properties(node)
	_eq(failures, "props.speed", props.get("speed"), 200.0)
	_eq(failures, "props.health", props.get("health"), 100)
	node.free()


func _test_node_info(failures: Array[String]) -> void:
	var root := Node2D.new()
	root.name = "Root"
	var player := CharacterBody2D.new()
	player.name = "Player"
	var sprite := Sprite2D.new()
	sprite.name = "Sprite2D"
	root.add_child(player)
	player.add_child(sprite)

	var info: Dictionary = Inspect.node_info(player, root)
	_eq(failures, "info.node_path", info.get("node_path"), "Player")
	_eq(failures, "info.type", info.get("type"), "CharacterBody2D")
	_eq(failures, "info.children", info.get("children"), ["Sprite2D"])
	# Root resolves to "." relative to itself.
	_eq(failures, "info.root_path", Inspect.node_info(root, root).get("node_path"), ".")
	root.free()
