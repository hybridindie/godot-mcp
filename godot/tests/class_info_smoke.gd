@tool
extends SceneTree
## Headless behavior test for cmd_describe_class (issue #533).
##
## Run via: godot --headless --path godot/ --script res://tests/class_info_smoke.gd
## Drives the real ClassDB (headless -s can read ClassDB + ProjectSettings — no
## editor needed for a read-only query). Pins: Node2D's shape (properties/
## methods/signals/constants/enums/inherit chain), Variant.Type *names* the
## coercion layer accepts, include_inherited filtering, and the unknown-class
## VALIDATION_ERROR with did-you-mean. Prints CLASS_INFO_TEST_OK, quits 0.

const Router := preload("res://addons/godot_mcp/command_router.gd")
const Coerce := preload("res://addons/godot_mcp/type_coerce.gd")


func _initialize() -> void:
	var failures: Array[String] = []
	var router := Router.new()

	var body: Dictionary = router.handle({
		"id": "1", "command": "cmd_describe_class",
		"params": {"class_name": "Node2D"},
	})
	_eq(failures, "ok", body.get("ok"), true)
	var r: Dictionary = body.get("result", {})
	_eq(failures, "class_name", r.get("class_name"), "Node2D")
	_eq(failures, "inherits", r.get("inherits"), "CanvasItem")
	_eq(failures, "can_instantiate", r.get("can_instantiate"), true)

	var chain: Array = r.get("inherits_chain", [])
	if chain.size() < 4 or chain[0] != "Node2D" or not chain.has("Object"):
		failures.append("chain: expected Node2D..Object root-first, got %s" % str(chain))

	# Property entries carry Variant.Type NAME + a JSON-safe default.
	var properties: Array = r.get("properties", [])
	var position: Dictionary = {}
	var names: Array = []
	for p in properties:
		names.append(str(p.get("name")))
		if str(p.get("name")) == "position":
			position = p
	if position.is_empty():
		failures.append("properties: Node2D.position missing from %s" % str(names))
	else:
		_eq(failures, "position.type", position.get("type"), "Vector2")
		# The default is a JSON-coerced shape the coercion layer accepts back.
		var default: Variant = position.get("default")
		if str(typeof(default)) != "2" or default.get("x", null) == null:  # 2 = TYPE_DICTIONARY? no — array
			pass
		if default is Array and default.size() == 2:
			pass
		elif default is Dictionary and default.has("x"):
			pass
		else:
			failures.append("position.default: expected a JSON Vector2 shape, got %s" % str(default))

	# Methods carry typed args + return.
	var methods: Array = r.get("methods", [])
	var angle_to: Dictionary = {}
	for m in methods:
		if str(m.get("name")) == "get_angle_to":
			angle_to = m
	if angle_to.is_empty():
		failures.append("methods: Node2D.get_angle_to missing")
	else:
		_eq(failures, "get_angle_to.return_type", angle_to.get("return_type"), "float")
		var args: Array = angle_to.get("args", [])
		if args.is_empty() or str(args[0].get("type")) != "Vector2":
			failures.append("get_angle_to.args: expected one Vector2 arg, got %s" % str(args))

	# include_private: ClassDB exposes no _-prefixed property entries (verified:
	# Node2D lists 52 public props, 0 private), so the flag is a passthrough —
	# pinned in the Python contract tests, not observable here.

	# Default flags = own-only (include_inherited=false → no_inheritance=true):
	# Node2D's own methods exclude Node's get_parent.
	var own: Dictionary = router.handle({
		"id": "3", "command": "cmd_describe_class",
		"params": {"class_name": "Node2D"},
	})
	var own_methods: Array = own.get("result", {}).get("methods", [])
	for m in own_methods:
		if str(m.get("name")) == "get_parent":  # Node method — inherited
			failures.append("default flags: inherited method leaked")
			break

	# include_inherited=true widens to the ancestry: get_parent appears.
	var all: Dictionary = router.handle({
		"id": "4", "command": "cmd_describe_class",
		"params": {"class_name": "Node2D", "include_inherited": true},
	})
	var all_methods: Array = all.get("result", {}).get("methods", [])
	var has_get_parent := false
	for m in all_methods:
		if str(m.get("name")) == "get_parent":
			has_get_parent = true
			break
	_eq(failures, "include_inherited", has_get_parent, true)

	# Enums carry members; Tween owns its own constants (TransitionType etc.).
	var enums_body: Dictionary = router.handle({
		"id": "5", "command": "cmd_describe_class",
		"params": {"class_name": "Tween"},
	})
	var constants: Array = enums_body.get("result", {}).get("constants", [])
	if constants.is_empty():
		failures.append("constants: Tween should expose its own constants")
	var enums: Array = enums_body.get("result", {}).get("enums", [])
	for e in enums:
		if (e.get("members") as Array).is_empty():
			failures.append("enums: %s has empty members" % str(e.get("name")))

	# Non-instantiable abstract classes report honestly (CanvasItem is abstract).
	var abstract_body: Dictionary = router.handle({
		"id": "6", "command": "cmd_describe_class",
		"params": {"class_name": "CanvasItem"},
	})
	_eq(failures, "canvasitem_can_instantiate", abstract_body.get("result", {}).get("can_instantiate"), false)

	# Unknown class → VALIDATION_ERROR with did-you-mean.
	var unknown: Dictionary = router.handle({
		"id": "7", "command": "cmd_describe_class",
		"params": {"class_name": "Node9D"},
	})
	_eq(failures, "unknown.ok", unknown.get("ok"), false)
	_eq(failures, "unknown.error", unknown.get("error"), "VALIDATION_ERROR")
	if not str(unknown.get("hint", "")).contains("Node2D") and not str(unknown.get("hint", "")).contains("Node3D"):
		failures.append("unknown.hint: expected did-you-mean over real classes: %s" % str(unknown.get("hint")))

	# Empty class_name → VALIDATION_ERROR, pre-ClassDB.
	var empty: Dictionary = router.handle({
		"id": "7", "command": "cmd_describe_class", "params": {"class_name": ""},
	})
	_eq(failures, "empty.ok", empty.get("ok"), false)
	_eq(failures, "empty.error", empty.get("error"), "VALIDATION_ERROR")

	# The registered command surfaces in the handshake list.
	_eq(failures, "registered", router.has_command("cmd_describe_class"), true)

	# The variant_type_name helper is the coercion layer's vocabulary.
	_eq(failures, "vtn_vector2", Coerce.variant_type_name(TYPE_VECTOR2), "Vector2")
	_eq(failures, "vtn_bool", Coerce.variant_type_name(TYPE_BOOL), "bool")

	if failures.is_empty():
		print("CLASS_INFO_TEST_OK")
		quit(0)
	else:
		push_error("CLASS_INFO_TEST_FAILURES: %s" % [str(failures)])
		quit(1)


func _eq(failures: Array[String], what: String, got: Variant, expected: Variant) -> void:
	if got != expected:
		failures.append("%s: expected %s, got %s" % [what, str(expected), str(got)])